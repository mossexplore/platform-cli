package platform

import (
	"context"
	"errors"
	"net/http"
	"net/netip"
	"net/url"
	"os"
	"strings"
)

type logProxySettings struct {
	address string
	bypass  string
}

var errInvalidDownloadProxy = errors.New("下载代理地址无效，请检查代理配置")

func signedDownloadProxy(ctx context.Context) func(*http.Request) (*url.URL, error) {
	settings := selectLogProxy(os.Environ(), func() logProxySettings {
		return systemLogProxy(ctx)
	})
	if settings.address == "" {
		return nil
	}
	address := settings.address
	if !strings.Contains(address, "://") {
		address = "http://" + address
	}
	proxy, err := url.Parse(address)
	valid := err == nil && proxy.Hostname() != "" && supportedLogProxyScheme(proxy.Scheme)
	return func(req *http.Request) (*url.URL, error) {
		if bypassLogProxy(req.URL, settings.bypass) {
			return nil, nil
		}
		if !valid {
			return nil, errInvalidDownloadProxy
		}
		return proxy, nil
	}
}

func supportedLogProxyScheme(scheme string) bool {
	switch scheme {
	case "http", "https", "socks5", "socks5h":
		return true
	default:
		return false
	}
}

func selectLogProxy(environment []string, system func() logProxySettings) logProxySettings {
	// urllib checks the environment as a whole before consulting OS settings.
	// Its lowercase variables override uppercase ones, including empty values.
	proxies := map[string]string{}
	cgi := false
	for _, entry := range environment {
		name, value, _ := strings.Cut(entry, "=")
		cgi = cgi || name == "REQUEST_METHOD"
		if key := strings.ToLower(name); value != "" && strings.HasSuffix(key, "_proxy") {
			proxies[key] = value
		}
	}
	if cgi {
		delete(proxies, "http_proxy")
	}
	for _, entry := range environment {
		name, value, _ := strings.Cut(entry, "=")
		if name != strings.ToLower(name) || !strings.HasSuffix(name, "_proxy") {
			continue
		}
		if value == "" {
			delete(proxies, name)
		} else {
			proxies[name] = value
		}
	}
	if len(proxies) == 0 {
		return system()
	}
	address := proxies["https_proxy"]
	if address == "" {
		address = proxies["all_proxy"]
	}
	return logProxySettings{address: address, bypass: proxies["no_proxy"]}
}

func bypassLogProxy(target *url.URL, bypass string) bool {
	host := strings.ToLower(target.Hostname())
	ip, _ := netip.ParseAddr(host)
	if host == "localhost" || ip.IsLoopback() {
		return true
	}
	if ip.IsValid() {
		host = ip.String()
	}
	port := target.Port()
	if port == "" {
		port = "443" // Signed downloads only accept HTTPS.
	}
	for _, entry := range strings.Split(bypass, ",") {
		rule := strings.ToLower(strings.TrimSpace(entry))
		switch rule {
		case "":
			continue
		case "<local>":
			if !ip.IsValid() && !strings.Contains(host, ".") {
				return true
			}
			continue
		}
		if prefix, err := netip.ParsePrefix(rule); err == nil {
			if prefix.Contains(ip) {
				return true
			}
			continue
		}
		if strings.Contains(rule, "://") {
			scheme, address, _ := strings.Cut(rule, "://")
			if scheme != "all" && scheme != target.Scheme {
				continue
			}
			rule = address
		}
		if proxyHostMatches(host, port, rule) {
			return true
		}
	}
	return false
}

func proxyHostMatches(host, port, rule string) bool {
	if rule == "*" {
		return true
	}
	if address, err := netip.ParseAddr(rule); err == nil {
		return host == address.String()
	}
	target, err := url.Parse("//" + rule)
	if err != nil || target.Hostname() == "" || (target.Port() != "" && target.Port() != port) {
		return false
	}
	name := strings.TrimPrefix(target.Hostname(), "*.")
	if address, err := netip.ParseAddr(name); err == nil {
		return host == address.String()
	}
	if name == "localhost" {
		return host == name
	}
	if strings.HasPrefix(target.Hostname(), "*.") {
		return strings.HasSuffix(host, "."+name)
	}
	if strings.HasPrefix(name, ".") {
		return strings.HasSuffix(host, name)
	}
	return host == name || strings.HasSuffix(host, "."+name)
}
