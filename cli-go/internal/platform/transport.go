package platform

import (
	"bytes"
	"context"
	"crypto/tls"
	"crypto/x509"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/breml/rootcerts/embedded"
	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
)

const maxResponseBytes = 8 << 20

func businessTransport(cfg localstate.Config) *http.Client {
	transport := http.DefaultTransport.(*http.Transport).Clone()
	transport.Proxy = nil
	verifyTLS := cfg.Profile().VerifyTLS
	if verifyTLS == nil {
		verifyTLS = cfg.API.VerifyTLS
	}
	if verifyTLS != nil && !*verifyTLS {
		// This setting belongs to platform HTTP only; the permission service always verifies TLS.
		transport.TLSClientConfig = &tls.Config{InsecureSkipVerify: true} // #nosec G402
	}
	return &http.Client{
		Transport: transport, Timeout: time.Duration(cfg.API.TimeoutMS) * time.Millisecond,
		CheckRedirect: rejectRedirect,
	}
}

func accessTransport(settings localstate.Access) (*http.Client, error) {
	roots, err := accessRoots(settings)
	if err != nil {
		return nil, err
	}
	transport := http.DefaultTransport.(*http.Transport).Clone()
	transport.TLSClientConfig = &tls.Config{RootCAs: roots}
	if !settings.UseEnvProxy {
		transport.Proxy = nil
	}
	return &http.Client{
		Transport: transport, Timeout: time.Duration(settings.TimeoutSecs * float64(time.Second)),
		CheckRedirect: rejectRedirect,
	}, nil
}

func accessRoots(settings localstate.Access) (*x509.CertPool, error) {
	// A dedicated pool deliberately ignores OS and environment roots in these modes.
	source := settings.CASource
	file, directory := "", ""
	switch source {
	case "certifi":
		pool := x509.NewCertPool()
		if !pool.AppendCertsFromPEM([]byte(embedded.MozillaCACertificatesPEM())) {
			return nil, errors.New("无法加载预览版随包公共 CA")
		}
		return pool, nil
	case "custom":
		file = settings.CAFile
	case "env":
		file = os.Getenv("SSL_CERT_FILE")
		if file == "" {
			directory = os.Getenv("SSL_CERT_DIR")
		}
	}
	if file == "" && directory == "" {
		return nil, nil
	}
	pool := x509.NewCertPool()
	if file != "" {
		pem, err := os.ReadFile(file)
		if err != nil || !pool.AppendCertsFromPEM(pem) {
			return nil, fmt.Errorf("无法加载权限服务的 %s CA 文件", source)
		}
		return pool, nil
	}
	entries, err := os.ReadDir(directory)
	if err != nil {
		return nil, errors.New("无法读取权限服务的 SSL_CERT_DIR")
	}
	found := false
	for _, entry := range entries {
		if entry.IsDir() {
			continue
		}
		pem, err := os.ReadFile(filepath.Join(directory, entry.Name()))
		if err == nil && pool.AppendCertsFromPEM(pem) {
			found = true
		}
	}
	if !found {
		return nil, errors.New("权限服务的 SSL_CERT_DIR 中没有可读取的 CA 证书")
	}
	return pool, nil
}

func rejectRedirect(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }

func requestJSON(ctx context.Context, client *http.Client, method, endpoint string, body any,
	headers http.Header, target string) (int, json.RawMessage, error) {
	var reader io.Reader
	if body != nil {
		encoded, err := json.Marshal(body)
		if err != nil {
			return 0, nil, fmt.Errorf("%s请求参数无效", target)
		}
		reader = bytes.NewReader(encoded)
	}
	req, err := http.NewRequestWithContext(ctx, method, endpoint, reader)
	if err != nil {
		return 0, nil, fmt.Errorf("%s地址无效", target)
	}
	req.Header = headers
	req.Header.Set("Accept", "application/json")
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	resp, err := client.Do(req)
	if err != nil {
		if ctx.Err() != nil {
			return 0, nil, ctx.Err()
		}
		return 0, nil, fmt.Errorf("%s请求失败，请检查网络和证书配置", target)
	}
	defer resp.Body.Close()
	data, err := io.ReadAll(io.LimitReader(resp.Body, maxResponseBytes+1))
	if err != nil || len(data) > maxResponseBytes {
		return resp.StatusCode, nil, fmt.Errorf("%s响应读取失败或超出预览版限制", target)
	}
	if !json.Valid(data) {
		if resp.StatusCode >= 200 && resp.StatusCode < 300 {
			return resp.StatusCode, nil, fmt.Errorf("%s响应不是有效 JSON", target)
		}
		return resp.StatusCode, nil, nil
	}
	return resp.StatusCode, json.RawMessage(strings.TrimSpace(string(data))), nil
}
