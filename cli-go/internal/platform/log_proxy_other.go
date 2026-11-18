//go:build !windows && !darwin

package platform

import "context"

func systemLogProxy(context.Context) logProxySettings {
	return logProxySettings{}
}
