package edgelogin

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"sync"
	"time"

	"github.com/chromedp/cdproto/network"
	"github.com/chromedp/cdproto/page"
	"github.com/chromedp/chromedp"
	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
)

type Summary struct {
	Environment string
	Username    string
	ChineseName string
	Department  string
	BusinessID  string
	AdminRole   string
	cookie      string
	csrfToken   string
}

func Run(ctx context.Context, paths localstate.Paths, cfg localstate.Config, progress io.Writer) (Summary, error) {
	return run(ctx, paths, cfg, progress, func(session browserSession) (string, error) {
		return paths.SaveLogin(session.credentials, session.catalog, session.businessID, session.scopeID)
	})
}

func Refresh(ctx context.Context, paths localstate.Paths, cfg localstate.Config, progress io.Writer) (Summary, error) {
	return run(ctx, paths, cfg, progress, func(session browserSession) (string, error) {
		return paths.SaveBusinessRefresh(session.credentials, session.catalog, session.businessID)
	})
}

func run(ctx context.Context, paths localstate.Paths, cfg localstate.Config, progress io.Writer,
	save func(browserSession) (string, error)) (Summary, error) {
	executable, err := installedEdge()
	if err != nil {
		return Summary{}, err
	}
	profile, err := cfg.RequireProfile()
	if err != nil {
		return Summary{}, err
	}
	if !strings.HasPrefix(profile.Origin(), "https://") {
		return Summary{}, errors.New("Go 客户端的 Edge 登录需要 HTTPS 平台地址")
	}
	unlock, err := paths.LockLogin()
	if err != nil {
		return Summary{}, err
	}
	defer unlock()

	timeout, cancelTimeout := context.WithTimeout(ctx, time.Duration(cfg.Browser.LoginTimeoutMS)*time.Millisecond)
	defer cancelTimeout()
	// The dedicated browser profile is bound to the environment and the configured endpoint.
	browserDir := paths.BrowserProfile(profile)
	allocator, stopAllocator := chromedp.NewExecAllocator(timeout,
		chromedp.ExecPath(executable), chromedp.UserDataDir(browserDir),
		chromedp.Flag("remote-debugging-address", "127.0.0.1"),
		chromedp.Flag("hide-crash-restore-bubble", true),
		chromedp.Flag("no-first-run", true), chromedp.Flag("no-default-browser-check", true))
	defer stopAllocator()
	browser, closeBrowser := chromedp.NewContext(allocator, chromedp.WithErrorf(browserErrorLogger(log.Printf)))
	defer closeBrowser()
	defer func() {
		if browser.Err() == nil && chromedp.FromContext(browser).Browser != nil {
			// Let Edge save its profile before the allocator terminates the process.
			shutdown, cancelShutdown := context.WithTimeout(browser, 3*time.Second)
			defer cancelShutdown()
			_ = chromedp.Cancel(shutdown)
		}
	}()
	userInfoURL := profile.Origin() + "/ai/user/info"
	attempt := &userInfoRequest{url: userInfoURL}
	chromedp.ListenTarget(browser, attempt.observe)
	environment := strings.TrimSpace(profile.Alias)
	if environment == "" {
		environment = profile.Name
	}
	environment = strings.Map(func(char rune) rune {
		if char < 32 || char == 127 {
			return ' '
		}
		return char
	}, environment)
	fmt.Fprintf(progress, "正在登录【%s】\n", environment)
	fmt.Fprintln(progress, "正在打开登录页面…")
	err = chromedp.Run(browser, network.Enable(), chromedp.ActionFunc(func(ctx context.Context) error {
		_, _, navigationError, _, err := page.Navigate(profile.Endpoint).Do(ctx)
		if err != nil || navigationError != "" {
			return errors.New("无法打开当前平台页面")
		}
		return nil
	}))
	if err != nil {
		if ctx.Err() != nil {
			return Summary{}, ctx.Err()
		}
		return Summary{}, errors.New("无法启动专用 Edge 或打开平台页面，请检查浏览器策略、证书及专用目录占用")
	}
	session, err := awaitLogin(browser, profile, attempt)
	if err != nil {
		if ctx.Err() != nil {
			return Summary{}, ctx.Err()
		}
		return Summary{}, err
	}
	creds := session.credentials
	now := time.Now()
	creds.AcquiredAt, _ = json.Marshal(now)
	creds.ChineseName, creds.Department = session.identity.ChineseName, session.identity.Department
	creds.IsSuperAdmin, creds.IsAISupporter = session.identity.IsSuperAdmin, session.identity.IsAISupporter
	expires := now.Add(time.Duration(cfg.Auth.TTLSeconds) * time.Second)
	creds.ExpiresAt, err = json.Marshal(expires)
	if err != nil {
		return Summary{}, errors.New("登录缓存有效期超出可保存范围")
	}
	session.credentials = creds
	id, err := save(session)
	if err != nil {
		return Summary{}, err
	}
	if id == "" {
		fmt.Fprintln(progress, "[提示] 未能自动选择业务，请用 ml business list 查看候选，再用 ml business TENANT_ID 选择")
	}
	return Summary{
		Environment: environment, Username: creds.Username, ChineseName: session.identity.ChineseName,
		Department: session.identity.Department, BusinessID: id, AdminRole: creds.AdminRoleLabel(), cookie: creds.Cookie, csrfToken: creds.CSRFToken,
	}, nil
}

func browserErrorLogger(logf func(string, ...any)) func(string, ...any) {
	return func(format string, args ...any) {
		// Login does not consume Network.responseReceivedExtraInfo. Older Edge
		// builds can report Private for its resourceIPAddressSpace field.
		const legacyAddressSpaceError = ` into Go network.IPAddressSpace within "/resourceIPAddressSpace": unknown IPAddressSpace value: Private`
		if format == "could not unmarshal event: %v" && len(args) == 1 {
			if err, ok := args[0].(error); ok && strings.HasSuffix(err.Error(), legacyAddressSpaceError) {
				return
			}
		}
		logf("ERROR: "+format, args...)
	}
}

func installedEdge() (string, error) {
	var candidates []string
	switch runtime.GOOS {
	case "windows":
		for _, variable := range []string{"ProgramFiles(x86)", "ProgramFiles", "LocalAppData"} {
			if base := os.Getenv(variable); base != "" && filepath.IsAbs(base) {
				candidates = append(candidates, filepath.Join(base, "Microsoft", "Edge", "Application", "msedge.exe"))
			}
		}
	case "darwin":
		const bundle = "Microsoft Edge.app/Contents/MacOS/Microsoft Edge"
		candidates = append(candidates, filepath.Join("/Applications", bundle))
		if home, err := os.UserHomeDir(); err == nil {
			candidates = append(candidates, filepath.Join(home, "Applications", bundle))
		}
	}
	for _, candidate := range candidates {
		if info, err := os.Stat(candidate); err == nil && info.Mode().IsRegular() {
			return candidate, nil
		}
	}
	return "", errors.New("未找到 Microsoft Edge 正式版，Go 预览登录需要系统已安装 Edge")
}

type userInfoRequest struct {
	mu       sync.Mutex
	url      string
	id       network.RequestID
	token    string
	accepted bool
	finished bool
}

func (capture *userInfoRequest) observe(event any) {
	capture.mu.Lock()
	defer capture.mu.Unlock()
	switch value := event.(type) {
	case *network.EventRequestWillBeSent:
		if capture.id == value.RequestID {
			capture.id, capture.token, capture.accepted, capture.finished = "", "", false, false
		}
		if value.Request.Method != http.MethodGet || !sameResource(value.Request.URL, capture.url) {
			return
		}
		for key, item := range value.Request.Headers {
			switch strings.ToLower(key) {
			case "csrftoken", "x-csrftoken", "x-csrf-token":
				if token, ok := item.(string); ok && token != "" {
					capture.id, capture.token, capture.accepted, capture.finished = value.RequestID, token, false, false
					return
				}
			}
		}
	case *network.EventResponseReceived:
		if value.RequestID == capture.id {
			capture.accepted = value.Response.Status == http.StatusOK && sameResource(value.Response.URL, capture.url)
		}
	case *network.EventLoadingFinished:
		if value.RequestID == capture.id {
			capture.finished = value.EncodedDataLength < 1<<20
		}
	}
}

func (capture *userInfoRequest) ready() (network.RequestID, string) {
	capture.mu.Lock()
	defer capture.mu.Unlock()
	if !capture.accepted || !capture.finished {
		return "", ""
	}
	return capture.id, capture.token
}

func sameResource(address, wanted string) bool {
	parsed, err := url.Parse(address)
	if err != nil || parsed.User != nil {
		return false
	}
	expected, err := url.Parse(wanted)
	if err != nil {
		return false
	}
	return parsed.Scheme == expected.Scheme && strings.EqualFold(parsed.Hostname(), expected.Hostname()) &&
		effectivePort(parsed) == effectivePort(expected) && strings.TrimSuffix(parsed.EscapedPath(), "/") == expected.EscapedPath()
}

func effectivePort(address *url.URL) string {
	if port := address.Port(); port != "" {
		return port
	}
	if address.Scheme == "https" {
		return "443"
	}
	return "80"
}

func (s Summary) Secrets() (string, string) { return s.cookie, s.csrfToken }

func (s Summary) PrintSecrets(out io.Writer) error {
	_, err := fmt.Fprintf(out, "cookie: %s\ncsrftoken: %s\n", s.cookie, s.csrfToken)
	return err
}
