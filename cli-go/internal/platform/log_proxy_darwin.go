package platform

import (
	"context"
	"net"
	"os/exec"
	"strings"
	"time"
)

func systemLogProxy(ctx context.Context) logProxySettings {
	ctx, cancel := context.WithTimeout(ctx, 2*time.Second)
	defer cancel()
	output, err := exec.CommandContext(ctx, "/usr/sbin/scutil", "--proxy").Output()
	if err != nil {
		return logProxySettings{}
	}
	return macHTTPSProxy(string(output))
}

func macHTTPSProxy(output string) logProxySettings {
	values := map[string]string{}
	var bypass []string
	depth := 0
	inExceptions := false
	for _, line := range strings.Split(output, "\n") {
		line = strings.TrimSpace(line)
		if line == "}" {
			depth--
			if depth == 1 {
				inExceptions = false
			}
			continue
		}
		key, value, ok := strings.Cut(line, " : ")
		if ok {
			switch {
			case depth == 1 && key == "ExceptionsList":
				inExceptions = true
			case depth == 1:
				values[key] = value
			case depth == 2 && inExceptions:
				bypass = append(bypass, value)
			}
		}
		if strings.HasSuffix(line, "{") {
			depth++
		}
	}
	if values["HTTPSEnable"] != "1" || values["HTTPSProxy"] == "" || values["HTTPSPort"] == "" {
		return logProxySettings{}
	}
	if values["ExcludeSimpleHostnames"] == "1" {
		bypass = append(bypass, "<local>")
	}
	return logProxySettings{
		address: net.JoinHostPort(strings.Trim(values["HTTPSProxy"], "[]"), values["HTTPSPort"]),
		bypass:  strings.Join(bypass, ","),
	}
}
