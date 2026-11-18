package platform

import (
	"net/url"
	"testing"
)

func TestSelectLogProxy(t *testing.T) {
	system := logProxySettings{"system-proxy:8080", "corp.test"}
	for _, tt := range []struct {
		name string
		env  []string
		want logProxySettings
	}{
		{"system fallback", nil, system},
		{"HTTPS before ALL", []string{"ALL_PROXY=generic:80", "HTTPS_PROXY=specific:80", "NO_PROXY=direct.test"}, logProxySettings{"specific:80", "direct.test"}},
		{"lowercase first", []string{"https_proxy=lower:80", "HTTPS_PROXY=upper:80"}, logProxySettings{address: "lower:80"}},
		{"empty lowercase override", []string{"HTTPS_PROXY=upper:80", "https_proxy=", "ALL_PROXY=generic:80"}, logProxySettings{address: "generic:80"}},
		{"HTTP route only", []string{"HTTP_PROXY=http-only:80"}, logProxySettings{}},
		{"explicit bypass", []string{"NO_PROXY=*"}, logProxySettings{bypass: "*"}},
	} {
		t.Run(tt.name, func(t *testing.T) {
			got := selectLogProxy(tt.env, func() logProxySettings { return system })
			if got != tt.want {
				t.Errorf("selected proxy = %+v, want %+v", got, tt.want)
			}
		})
	}
}

func TestBypassLogProxy(t *testing.T) {
	for _, tt := range []struct {
		host string
		rule string
		want bool
	}{
		{"obs.test", "other.test, *", true},
		{"obs.test", "obs.test", true},
		{"private.obs.test", "OBS.TEST", true},
		{"fakeobs.test", "obs.test", false},
		{"obs.test", ".obs.test", false},
		{"private.obs.test", "*.obs.test", true},
		{"obs.test", "obs.test:443", true},
		{"obs.test:8443", "obs.test:443", false},
		{"obs.test", "http://obs.test", false},
		{"obs.test", "https://obs.test", true},
		{"internal", "<local>", true},
		{"192.168.3.6", "192.168.0.0/16", true},
		{"[2001:0db8::1]", "2001:db8::1", true},
		{"127.0.0.1", "", true},
	} {
		target, err := url.Parse("https://" + tt.host + "/logs")
		if err != nil {
			t.Fatal(err)
		}
		if got := bypassLogProxy(target, tt.rule); got != tt.want {
			t.Errorf("bypass %q with rule %q = %v, want %v", tt.host, tt.rule, got, tt.want)
		}
	}
}
