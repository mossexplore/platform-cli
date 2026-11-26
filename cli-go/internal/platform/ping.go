package platform

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"slices"
	"strings"
	"time"

	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
)

var ErrSessionExpired = errors.New("平台会话已失效")

func (s Session) Probe(ctx context.Context, creds localstate.Credentials, business, requestID string, commit func(cookie, csrf string) error) error {
	profile := s.Config.Profile()
	client := businessTransport(s.Config)
	defer client.CloseIdleConnections()
	body, _ := json.Marshal(map[string]string{"businessId": business})
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, profile.Origin()+"/ai/backend/mep/tenant/queryTeamList", bytes.NewReader(body))
	if err != nil {
		return err
	}
	metadata := invocation{version: s.CLIVersion, id: localstate.NewID(), installation: s.Paths.InstallationID(), stderr: s.Stderr}
	request.Header = metadata.headers(business)
	request.Header.Set("X-Request-ID", requestID)
	request.Header.Set("ai-businessId", business)
	setPlatformCookie(request.Header, creds.Cookie)
	request.Header.Set("csrftoken", creds.CSRFToken)
	request.Header.Set("Referer", profile.PublicEndpoint())
	request.Header.Set("Content-Type", "application/json")
	response, err := client.Do(request)
	if err != nil {
		return errors.New("平台保活连接失败")
	}
	defer response.Body.Close()
	status := response.StatusCode
	if status == 401 || status == 403 || status == 419 || status == 440 || status >= 300 && status < 400 {
		return ErrSessionExpired
	}
	data, err := io.ReadAll(io.LimitReader(response.Body, maxResponseBytes+1))
	if err != nil || len(data) > maxResponseBytes || status < 200 || status >= 300 {
		return errors.New("平台保活请求失败")
	}
	if err := metadata.checkVersion(data); err != nil {
		return err
	}
	var envelope Record
	if json.Unmarshal(data, &envelope) == nil {
		code := envelope.Object("result")["code"]
		if slices.Contains([]string{"401", "403", "419", "440", `"UNAUTHORIZED"`, `"SESSION_EXPIRED"`}, string(code)) {
			return ErrSessionExpired
		}
	}
	if _, err := Result(data, "平台保活", false); err != nil {
		return err
	}
	// Only this endpoint and the same selected business can update these credentials.
	cookies := request.Cookies()
	for _, next := range response.Cookies() {
		if next == nil || next.Valid() != nil {
			continue
		}
		cookies = slices.DeleteFunc(cookies, func(old *http.Cookie) bool { return old.Name == next.Name })
		if next.MaxAge >= 0 {
			cookies = append(cookies, next)
		}
	}
	values := []string{}
	csrf := response.Header.Get("csrftoken")
	if csrf == "" {
		csrf = response.Header.Get("x-csrftoken")
	}
	for _, item := range cookies {
		plain := (&http.Cookie{Name: item.Name, Value: item.Value}).String()
		if plain != "" {
			values = append(values, plain)
		}
		if csrf == "" && item.Name == "csrftoken" {
			csrf = item.Value
		}
	}
	return commit(strings.Join(values, "; "), csrf)
}

func (a *API) RecordActivity() (string, string, string, bool) {
	if !a.confirmed {
		return "", "", "", false
	}
	ttl := time.Duration(a.session.Config.Auth.TTLSeconds) * time.Second
	_ = a.session.Paths.ExtendCredentials(a.profile, a.credentials, a.businessID, "", "", ttl)
	return a.profile.Name, a.credentials.Username, a.profile.Origin(), true
}

func confirmedPlatform(payload json.RawMessage) bool {
	var envelope Record
	if json.Unmarshal(payload, &envelope) != nil {
		return json.Valid(payload)
	}
	result := envelope.Object("result")
	code, exists := result["code"]
	return !exists || string(code) == "0"
}
