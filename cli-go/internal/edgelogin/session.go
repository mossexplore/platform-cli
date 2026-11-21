package edgelogin

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"strings"
	"time"

	"github.com/chromedp/cdproto/network"
	"github.com/chromedp/chromedp"
	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
)

type browserSession struct {
	credentials localstate.Credentials
	catalog     []localstate.Department
	businessID  string
	identity    userInfo
}

func awaitLogin(ctx context.Context, profile localstate.Profile, capture *userInfoRequest) (browserSession, error) {
	var stored struct {
		BusinessList string `json:"businessList"`
		BusinessID   string `json:"businessID"`
	}
	origin, _ := json.Marshal(profile.Origin())
	expression := `location.origin === new URL(` + string(origin) + `).origin ? ({
		businessList: (localStorage.getItem('ai-businessList') || '').slice(0, 4194305),
		businessID: (localStorage.getItem('ai-businessId') || '').slice(0, 1024)
	}) : ({})`
	ticker := time.NewTicker(300 * time.Millisecond)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return browserSession{}, errors.New("等待 Edge 登录或读取业务目录超时，或 Edge 窗口已关闭")
		case <-ticker.C:
		}
		id, token := capture.ready()
		if id == "" || !validToken(token) {
			continue
		}
		stored.BusinessList, stored.BusinessID = "", ""
		var body []byte
		var cookies []*network.Cookie
		err := chromedp.Run(ctx, chromedp.Evaluate(expression, &stored), chromedp.ActionFunc(func(target context.Context) error {
			if stored.BusinessList == "" || len(stored.BusinessList) > 4<<20 {
				return nil
			}
			var err error
			body, err = network.GetResponseBody(id).Do(target)
			if err != nil || len(body) > 1<<20 {
				body = nil
				return err
			}
			cookies, err = network.GetCookies().WithURLs([]string{capture.url}).Do(target)
			return err
		}))
		if err != nil || len(cookies) == 0 {
			continue
		}
		identity := parseUserInfo(body)
		catalog, err := parseCatalog(stored.BusinessList)
		if identity.Username == "" || err != nil {
			continue
		}
		var request http.Request
		request.Header = make(http.Header)
		for _, cookie := range cookies {
			httpCookie := &http.Cookie{Name: cookie.Name, Value: cookie.Value}
			if httpCookie.Valid() != nil {
				continue
			}
			request.AddCookie(httpCookie)
		}
		if request.Header.Get("Cookie") == "" {
			continue
		}
		return browserSession{
			credentials: localstate.Credentials{
				Origin: profile.Origin(), Profile: profile.Name, Username: identity.Username,
				Cookie: request.Header.Get("Cookie"), CSRFToken: token,
			},
			catalog: catalog, businessID: stored.BusinessID, identity: identity,
		}, nil
	}
}

func validToken(value string) bool {
	return value != "" && strings.TrimSpace(value) == value &&
		strings.IndexFunc(value, func(r rune) bool { return r < 32 || r == 127 }) == -1
}

type userInfo struct {
	Username      string
	ChineseName   string
	Department    string
	IsSuperAdmin  *bool
	IsAISupporter *bool
}

func parseUserInfo(body []byte) userInfo {
	var response struct {
		Result struct {
			Code          *int            `json:"code"`
			Username      string          `json:"username"`
			ChineseName   json.RawMessage `json:"cnName"`
			Department    json.RawMessage `json:"department"`
			IsSuperAdmin  json.RawMessage `json:"isSuperAdmin"`
			IsAISupporter json.RawMessage `json:"isAISupporter"`
		} `json:"result"`
	}
	if json.Unmarshal(body, &response) != nil || response.Result.Code == nil || *response.Result.Code != 0 {
		return userInfo{}
	}
	if len(response.Result.Username) > 128 || !validToken(response.Result.Username) {
		return userInfo{}
	}
	result := userInfo{Username: response.Result.Username}
	_ = json.Unmarshal(response.Result.ChineseName, &result.ChineseName)
	_ = json.Unmarshal(response.Result.Department, &result.Department)
	var superAdmin, aiSupporter *bool
	if json.Unmarshal(response.Result.IsSuperAdmin, &superAdmin) == nil {
		result.IsSuperAdmin = superAdmin
	}
	if json.Unmarshal(response.Result.IsAISupporter, &aiSupporter) == nil {
		result.IsAISupporter = aiSupporter
	}
	return result
}
