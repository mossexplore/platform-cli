package platform

import "testing"

func TestWindowsHTTPSProxy(t *testing.T) {
	for input, want := range map[string]string{
		"one-proxy:8080":                             "one-proxy:8080",
		"http://one-proxy:8080":                      "http://one-proxy:8080",
		"http=intranet:8080;https=secure-proxy:8080": "secure-proxy:8080",
		"https=http://secure-proxy:8080":             "http://secure-proxy:8080",
		"http=http://intranet:8080":                  "",
		"http=intranet:8080;socks=socks-proxy:1080":  "",
	} {
		if got := windowsHTTPSProxy(input); got != want {
			t.Errorf("system proxy for %q = %q, want %q", input, got, want)
		}
	}
}
