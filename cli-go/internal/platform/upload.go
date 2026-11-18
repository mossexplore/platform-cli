package platform

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"time"
)

func (a *API) Upload(ctx context.Context, path string, query url.Values, metadata any, filePath string,
	timeout time.Duration, maxSize int64) (json.RawMessage, error) {
	file, err := os.Open(filePath)
	if err != nil {
		return nil, fmt.Errorf("无法读取上传文件：%w", err)
	}
	defer file.Close()
	info, err := file.Stat()
	if err != nil || !info.Mode().IsRegular() || info.Size() > maxSize {
		return nil, errors.New("上传文件无效或超过大小上限")
	}
	meta, err := json.Marshal(metadata)
	if err != nil {
		return nil, err
	}
	var envelope bytes.Buffer
	multi := multipart.NewWriter(&envelope)
	if err := multi.WriteField("params", string(meta)); err != nil {
		return nil, err
	}
	if _, err := multi.CreateFormFile("file", filepath.Base(filePath)); err != nil {
		return nil, err
	}
	index := envelope.Len()
	if err := multi.Close(); err != nil {
		return nil, err
	}
	endpoint, err := a.endpoint(path, query)
	if err != nil {
		return nil, err
	}
	buffer := envelope.Bytes()
	body := io.MultiReader(bytes.NewReader(buffer[:index]), io.LimitReader(file, info.Size()), bytes.NewReader(buffer[index:]))
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, endpoint, body)
	if err != nil {
		return nil, errors.New("上传请求参数无效")
	}
	req.ContentLength = int64(len(buffer)) + info.Size()
	req.Header = a.headers()
	req.Header.Set("Accept", "application/json")
	req.Header.Set("Content-Type", multi.FormDataContentType())
	unlock, err := a.beginMutation(ctx)
	if err != nil {
		return nil, err
	}
	defer unlock()
	a.used = true
	client := *a.client
	client.Timeout = timeout
	response, err := client.Do(req)
	if err != nil {
		return nil, errors.New("上传结果未确认，请查询目标目录核实后再决定是否重试")
	}
	defer response.Body.Close()
	payload, err := io.ReadAll(io.LimitReader(response.Body, maxResponseBytes+1))
	if err != nil || len(payload) > maxResponseBytes {
		return nil, errors.New("上传结果未确认，请查询目标目录核实")
	}
	if err := a.metadata.checkVersion(payload); err != nil {
		return nil, err
	}
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		return nil, fmt.Errorf("上传结果未确认，HTTP %d，请查询目标目录核实", response.StatusCode)
	}
	if !json.Valid(payload) {
		return nil, errors.New("上传响应不是有效 JSON，请查询目标目录核实")
	}
	return payload, nil
}
