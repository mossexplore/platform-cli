package platform

import (
	"bufio"
	"bytes"
	"context"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"time"
)

const maxUpgradeBytes = 256 << 20

var msiFileHeader = []byte{0xd0, 0xcf, 0x11, 0xe0, 0xa1, 0xb1, 0x1a, 0xe1}

// DownloadUpgradeMSI uses HTTPS with certificate verification and sends no platform credentials.
func DownloadUpgradeMSI(ctx context.Context, address, destination string, progress func(int64, int64)) error {
	transport := signedDownloadTransport(ctx)
	defer transport.CloseIdleConnections()
	client := &http.Client{
		Transport: transport, Timeout: 10 * time.Minute,
		CheckRedirect: func(req *http.Request, via []*http.Request) error {
			if len(via) > 5 || !validSignedURL(req.URL) {
				return errors.New("升级下载的重定向无效")
			}
			return nil
		},
	}
	return downloadUpgradeMSI(ctx, client, address, destination, progress)
}

func downloadUpgradeMSI(ctx context.Context, client *http.Client, address, destination string, progress func(int64, int64)) error {
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, address, nil)
	if err != nil || !validSignedURL(request.URL) {
		return errors.New("升级下载地址必须使用 HTTPS")
	}
	response, err := client.Do(request)
	if err != nil {
		if ctx.Err() != nil {
			return ctx.Err()
		}
		return downloadNetworkError(err)
	}
	defer response.Body.Close()
	return saveUpgradeMSI(response, destination, progress)
}

func saveUpgradeMSI(response *http.Response, destination string, progress func(int64, int64)) error {
	if response.StatusCode != http.StatusOK {
		return fmt.Errorf("升级包下载失败，HTTP %d", response.StatusCode)
	}
	if response.ContentLength > maxUpgradeBytes {
		return errors.New("升级包超过 256 MiB")
	}
	body := bufio.NewReader(response.Body)
	header, err := body.Peek(len(msiFileHeader))
	if err != nil || !bytes.Equal(header, msiFileHeader) {
		return errors.New("升级说明地址未返回 MSI 安装包，请通过浏览器打开链接")
	}
	file, err := os.OpenFile(destination, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
	if err != nil {
		return errors.New("无法创建本地升级包")
	}
	var writer io.Writer = file
	if progress != nil {
		writer = &downloadProgressWriter{Writer: file, total: response.ContentLength, report: progress}
	}
	size, err := io.Copy(writer, io.LimitReader(body, maxUpgradeBytes+1))
	closeErr := file.Close()
	if size > maxUpgradeBytes {
		return errors.New("升级包超过 256 MiB")
	}
	if err != nil || closeErr != nil || response.ContentLength >= 0 && size != response.ContentLength {
		return errors.New("升级包下载未完成")
	}
	return nil
}
