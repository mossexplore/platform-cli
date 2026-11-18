package platform

import (
	"context"
	"strings"

	"golang.org/x/sys/windows/registry"
)

func systemLogProxy(context.Context) logProxySettings {
	key, err := registry.OpenKey(registry.CURRENT_USER,
		`Software\Microsoft\Windows\CurrentVersion\Internet Settings`, registry.QUERY_VALUE)
	if err != nil {
		return logProxySettings{}
	}
	defer key.Close()
	enabled, _, err := key.GetIntegerValue("ProxyEnable")
	if err != nil || enabled == 0 {
		return logProxySettings{}
	}
	server, _, _ := key.GetStringValue("ProxyServer")
	bypass, _, _ := key.GetStringValue("ProxyOverride")
	return logProxySettings{
		address: windowsHTTPSProxy(server),
		bypass:  strings.ReplaceAll(bypass, ";", ","),
	}
}

func windowsHTTPSProxy(server string) string {
	if prefix, _, assigned := strings.Cut(server, "="); !assigned || strings.Contains(prefix, "://") {
		// A single server without a protocol assignment handles HTTPS via CONNECT.
		return strings.TrimSpace(server)
	}
	for _, entry := range strings.Split(server, ";") {
		protocol, address, _ := strings.Cut(entry, "=")
		if strings.EqualFold(strings.TrimSpace(protocol), "https") {
			return strings.TrimSpace(address)
		}
	}
	return ""
}
