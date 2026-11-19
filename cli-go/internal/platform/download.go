package platform

import (
	"bytes"
	"compress/gzip"
	"context"
	"crypto/tls"
	"errors"
	"fmt"
	"io"
	"mime"
	"net"
	"net/http"
	"net/url"
	"os"
	"path"
	"path/filepath"
	"regexp"
	"strings"
	"time"
	"unicode"
)

func (a *API) stream(ctx context.Context, endpoint string, query url.Values, inspectJSON bool) (*http.Response, error) {
	address, err := a.endpoint(endpoint, query)
	if err != nil {
		return nil, err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, address, nil)
	if err != nil {
		return nil, fmt.Errorf("下载地址无效")
	}
	req.Header = a.headers()
	req.Header.Set("Accept-Encoding", "identity")
	a.used = true
	response, err := a.client.Do(req)
	if err != nil {
		if ctx.Err() != nil {
			return nil, ctx.Err()
		}
		return nil, fmt.Errorf("平台下载请求失败")
	}
	failed := response.StatusCode < 200 || response.StatusCode >= 300
	if failed || (inspectJSON && strings.Contains(strings.ToLower(response.Header.Get("Content-Type")), "json")) {
		defer response.Body.Close()
		body, _ := io.ReadAll(io.LimitReader(response.Body, maxResponseBytes))
		if err := a.metadata.checkVersion(body); err != nil {
			return nil, err
		}
		if failed {
			return nil, fmt.Errorf("平台下载失败，HTTP %d", response.StatusCode)
		}
		return nil, fmt.Errorf("导出接口返回 JSON，未收到配置文件")
	}
	return response, nil
}

func SafeDownloadName(disposition, fallback string) string {
	_, fields, _ := mime.ParseMediaType(disposition)
	return sanitizeDownloadName(fields["filename"], fallback)
}

func sanitizeDownloadName(value, fallback string) string {
	name := path.Base(strings.ReplaceAll(value, "\\", "/"))
	name = strings.Trim(strings.Map(func(r rune) rune {
		if unicode.IsControl(r) || strings.ContainsRune(`<>:"/\|?*`, r) {
			return '_'
		}
		return r
	}, name), " .")
	if name == "" || reservedWindowsName.MatchString(name) {
		return fallback
	}
	return name
}

var reservedWindowsName = regexp.MustCompile(`(?i)^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\.|$)`)
var invalidResourceName = regexp.MustCompile(`[^a-zA-Z0-9_-]`)

func (a *API) ExportTrain(ctx context.Context, taskID, destination string) (string, int64, error) {
	query := url.Values{"taskId": {taskID}, "businessId": {a.BusinessID()}}
	response, err := a.stream(ctx, trainInstancePrefix+"export", query, true)
	if err != nil {
		return "", 0, err
	}
	defer response.Body.Close()
	if destination == "" {
		fallback := invalidResourceName.ReplaceAllString(taskID, "_") + ".yaml"
		if reservedWindowsName.MatchString(fallback) {
			fallback = "task.yaml"
		}
		destination = SafeDownloadName(response.Header.Get("Content-Disposition"), fallback)
	}
	return SaveDownload(destination, response)
}

func SaveDownload(destination string, response *http.Response) (string, int64, error) {
	return saveDownload(destination, response, nil)
}

func saveDownload(destination string, response *http.Response, progress func(received, total int64)) (string, int64, error) {
	target, err := filepath.Abs(destination)
	if err != nil {
		return "", 0, fmt.Errorf("目标文件路径无效")
	}
	output, err := os.CreateTemp(filepath.Dir(target), ".ml-download-*.part")
	if err != nil {
		return "", 0, fmt.Errorf("无法在目标目录创建下载文件：%w", err)
	}
	defer os.Remove(output.Name())
	var writer io.Writer = output
	if progress != nil {
		progress(0, response.ContentLength)
		writer = &downloadProgressWriter{Writer: output, total: response.ContentLength, report: progress}
	}
	size, err := io.Copy(writer, response.Body)
	if err == nil && response.ContentLength >= 0 && size != response.ContentLength {
		err = fmt.Errorf("实际大小与 Content-Length 不一致")
	}
	if err == nil {
		err = output.Sync()
	}
	if closeErr := output.Close(); err == nil {
		err = closeErr
	}
	if err != nil {
		return "", 0, fmt.Errorf("下载文件未完整保存：%w", err)
	}
	extension := filepath.Ext(target)
	stem := strings.TrimSuffix(target, extension)
	for index, candidate := 0, target; ; index++ {
		if index > 0 {
			candidate = fmt.Sprintf("%s (%d)%s", stem, index, extension)
		}
		err := os.Link(output.Name(), candidate)
		if err == nil {
			return candidate, size, nil
		}
		if !os.IsExist(err) {
			return "", 0, fmt.Errorf("无法保存下载文件：%w", err)
		}
	}
}

type downloadProgressWriter struct {
	io.Writer
	total, received int64
	report          func(received, total int64)
}

func (w *downloadProgressWriter) Write(data []byte) (int, error) {
	n, err := w.Writer.Write(data)
	w.received += int64(n)
	w.report(w.received, w.total)
	return n, err
}

type LogDownloadEvents struct {
	Start    func()
	Progress func(received, total int64)
}

func (a *API) SignedDownload(ctx context.Context, raw, destination, fallback string, useURLName bool) (string, int64, error) {
	client := businessTransport(a.session.Config)
	client.Transport.(*http.Transport).Proxy = signedDownloadProxy(ctx)
	return signedDownload(ctx, client, raw, destination, ".", fallback, useURLName, LogDownloadEvents{})
}

func (a *API) SignedLogDownload(ctx context.Context, raw, destination, directory, name string, events LogDownloadEvents) (string, int64, error) {
	// Match the Python log downloader. OBS can use private trust roots and a
	// different network route from the console API. No platform headers or cookies
	// are used for this client.
	transport := signedDownloadTransport(ctx)
	transport.TLSClientConfig = &tls.Config{InsecureSkipVerify: true} // #nosec G402
	client := &http.Client{Transport: transport, CheckRedirect: rejectRedirect}
	return signedDownload(ctx, client, raw, destination, directory, name, false, events)
}

func LogDownloadName(value string) string {
	return sanitizeDownloadName(value, "download-logs")
}

func signedDownload(ctx context.Context, client *http.Client, raw, destination, directory, fallback string, useURLName bool, events LogDownloadEvents) (string, int64, error) {
	address, err := url.Parse(raw)
	if err != nil || !validSignedURL(address) {
		return "", 0, fmt.Errorf("下载地址为空或不是有效的 HTTPS 地址")
	}
	if events.Start != nil {
		events.Start()
	}
	client.Timeout = 60 * time.Second
	defer client.CloseIdleConnections()
	for redirects := 0; redirects <= 5; redirects++ {
		req, err := http.NewRequestWithContext(ctx, http.MethodGet, address.String(), nil)
		if err != nil {
			return "", 0, fmt.Errorf("下载地址无效")
		}
		req.Header.Set("Accept-Encoding", "identity")
		response, err := client.Do(req)
		if err != nil {
			if ctx.Err() != nil {
				return "", 0, ctx.Err()
			}
			return "", 0, downloadNetworkError(err)
		}
		switch response.StatusCode {
		case 301, 302, 303, 307, 308:
			_ = response.Body.Close()
			address, err = response.Location()
			if err != nil || !validSignedURL(address) {
				return "", 0, fmt.Errorf("下载跳转地址无效")
			}
			continue
		case 200:
			defer response.Body.Close()
			if strings.Contains(strings.ToLower(response.Header.Get("Content-Type")), "json") {
				return "", 0, fmt.Errorf("下载地址返回 JSON 而不是文件")
			}
			if destination == "" {
				name := fallback
				if useURLName {
					name = sanitizeDownloadName(path.Base(address.Path), fallback)
				}
				destination = filepath.Join(directory, SafeDownloadName(response.Header.Get("Content-Disposition"), name))
			}
			if !strings.HasSuffix(strings.ToLower(destination), ".zip") {
				destination += ".zip"
			}
			return saveDownload(destination, response, events.Progress)
		default:
			_ = response.Body.Close()
			return "", 0, fmt.Errorf("文件下载失败，HTTP %d", response.StatusCode)
		}
	}
	return "", 0, fmt.Errorf("下载重定向次数过多")
}

func downloadNetworkError(err error) error {
	// net/http includes the whole signed URL in errors. Report only the
	// category so credentials in a URL or proxy address never reach the output.
	var cert *tls.CertificateVerificationError
	var dns *net.DNSError
	var op *net.OpError
	var network net.Error
	switch {
	case errors.Is(err, errInvalidDownloadProxy):
		return errInvalidDownloadProxy
	case errors.As(err, &cert):
		return errors.New("下载网络请求失败：HTTPS 证书验证失败")
	case errors.As(err, &network) && network.Timeout():
		return errors.New("下载网络请求失败：连接或等待响应超时")
	case errors.As(err, &op) && op.Op == "proxyconnect":
		return errors.New("下载网络请求失败：无法通过代理建立连接")
	case errors.As(err, &dns):
		return errors.New("下载网络请求失败：无法解析下载主机")
	default:
		return errors.New("下载网络请求失败：无法建立连接或连接已中断")
	}
}

func validSignedURL(address *url.URL) bool {
	return address != nil && address.Scheme == "https" && address.Hostname() != "" && address.User == nil
}

func (a *API) ExportFeatures(ctx context.Context, id, language, destination string) (string, int64, error) {
	query := url.Values{"setId": {id}, "businessId": {a.BusinessID()}, "lang": {language}}
	// The server can advertise CSV as JSON. Inspect the decoded body instead.
	response, err := a.stream(ctx, "/ai/backend/dpp/proxy/featureStore/featureset/exportFeatures", query, false)
	if err != nil {
		return "", 0, err
	}
	defer response.Body.Close()
	if destination == "" {
		destination = SafeDownloadName(response.Header.Get("Content-Disposition"), "featuresInSet.csv")
		if !strings.HasSuffix(strings.ToLower(destination), ".csv") {
			destination += ".csv"
		}
	}
	input := io.Reader(response.Body)
	if strings.EqualFold(response.Header.Get("Content-Encoding"), "gzip") {
		decoded, err := gzip.NewReader(input)
		if err != nil {
			return "", 0, fmt.Errorf("特征集导出响应压缩格式无效")
		}
		defer decoded.Close()
		response.ContentLength = -1
		input = decoded
	}
	prefix, err := io.ReadAll(io.LimitReader(input, 65536))
	if err != nil {
		return "", 0, fmt.Errorf("无法读取特征集导出响应")
	}
	data := strings.TrimSpace(strings.TrimPrefix(string(prefix), "\ufeff"))
	if data == "" {
		return "", 0, fmt.Errorf("特征集导出失败：响应内容为空")
	}
	if strings.HasPrefix(data, "{") || strings.HasPrefix(data, "[") {
		if err := a.metadata.checkVersion([]byte(data)); err != nil {
			return "", 0, err
		}
		return "", 0, fmt.Errorf("特征集导出失败：接口返回 JSON，未返回 CSV 文件")
	}
	for _, html := range []string{"<!doctype html", "<html", "<head", "<body"} {
		if strings.HasPrefix(strings.ToLower(data), html) {
			return "", 0, fmt.Errorf("特征集导出返回 HTML 页面，请重新登录")
		}
	}
	copy := *response
	copy.Body = io.NopCloser(io.MultiReader(bytes.NewReader(prefix), input))
	return SaveDownload(destination, &copy)
}
