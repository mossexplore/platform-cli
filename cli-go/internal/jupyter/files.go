package jupyter

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"unicode"
	"unicode/utf8"

	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
	"github.com/mossexplore/platform-cli/cli-go/internal/platform"
)

func RemotePath(path string) (string, error) {
	if strings.HasPrefix(path, "/") || strings.Contains(path, "\\") || strings.IndexFunc(path, unicode.IsControl) >= 0 {
		return "", errors.New("远程路径必须相对 Jupyter 根目录")
	}
	var parts []string
	for _, part := range strings.Split(path, "/") {
		switch part {
		case "", ".":
			continue
		case "..":
			return "", errors.New("远程路径不可包含 ..")
		}
		parts = append(parts, part)
	}
	return strings.Join(parts, "/"), nil
}

func target(path string) (string, error) {
	normalized, err := RemotePath(path)
	if err != nil {
		return "", err
	}
	if normalized == "" {
		return "", errors.New("此操作不能以 Jupyter 根目录为目标")
	}
	return normalized, nil
}

func contents(path string) string {
	segments := strings.Split(path, "/")
	for i, segment := range segments {
		segments[i] = url.PathEscape(segment)
	}
	return "api/contents/" + strings.Join(segments, "/")
}

func (c *Client) Get(ctx context.Context, path string, content bool, format string) (platform.Record, error) {
	normalized, err := RemotePath(path)
	if err != nil {
		return nil, err
	}
	query := url.Values{"content": {"0"}}
	if content {
		query.Set("content", "1")
	}
	if format != "" {
		query.Set("type", "file")
		query.Set("format", format)
	}
	payload, err := c.JSON(ctx, http.MethodGet, contents(normalized), query, nil)
	if err != nil {
		return nil, err
	}
	var model platform.Record
	if json.Unmarshal(payload, &model) != nil || model.Text("type") == "" {
		return nil, errors.New("Jupyter 文件响应缺少有效的 type")
	}
	return model, nil
}

func (c *Client) absent(ctx context.Context, path string, overwrite bool) error {
	model, err := c.Get(ctx, path, false, "")
	if err != nil {
		var status StatusError
		if errors.As(err, &status) && status.Code == 404 {
			return nil
		}
		return err
	}
	if model.Text("type") == "directory" || !overwrite {
		return errors.New("目标已存在；文件覆盖须显式指定 --overwrite，目录不能被覆盖")
	}
	return nil
}

func (c *Client) Save(ctx context.Context, path string, data []byte, overwrite, text bool) (json.RawMessage, error) {
	path, err := target(path)
	if err != nil {
		return nil, err
	}
	format, content := "base64", ""
	if text {
		if !utf8.Valid(data) {
			return nil, errors.New("写入内容不是 UTF-8")
		}
		format, content = "text", string(data)
	} else {
		content = base64.StdEncoding.EncodeToString(data)
	}
	if err := c.absent(ctx, path, overwrite); err != nil {
		return nil, err
	}
	return c.JSON(ctx, http.MethodPut, contents(path), nil, map[string]string{"type": "file", "format": format, "content": content})
}

func (c *Client) Mkdir(ctx context.Context, path string) (json.RawMessage, error) {
	path, err := target(path)
	if err != nil {
		return nil, err
	}
	if err := c.absent(ctx, path, false); err != nil {
		return nil, err
	}
	return c.JSON(ctx, http.MethodPut, contents(path), nil, map[string]string{"type": "directory"})
}

func (c *Client) Move(ctx context.Context, source, destination string) (json.RawMessage, error) {
	source, err := target(source)
	if err != nil {
		return nil, err
	}
	destination, err = target(destination)
	if err != nil {
		return nil, err
	}
	if err := c.absent(ctx, destination, false); err != nil {
		return nil, err
	}
	return c.JSON(ctx, http.MethodPatch, contents(source), nil, map[string]string{"path": destination})
}

func (c *Client) Copy(ctx context.Context, source, directory string) (json.RawMessage, error) {
	source, err := target(source)
	if err != nil {
		return nil, err
	}
	directory, err = RemotePath(directory)
	if err != nil {
		return nil, err
	}
	model, err := c.Get(ctx, source, false, "")
	if err != nil {
		return nil, err
	}
	if model.Text("type") == "directory" {
		return nil, errors.New("copy 仅支持单文件，不支持递归目录复制")
	}
	model, err = c.Get(ctx, directory, false, "")
	if err != nil {
		return nil, err
	}
	if model.Text("type") != "directory" {
		return nil, errors.New("复制目标必须是已有目录")
	}
	return c.JSON(ctx, http.MethodPost, contents(directory), nil, map[string]string{"copy_from": source})
}

func (c *Client) Delete(ctx context.Context, path string) (map[string]any, error) {
	path, err := target(path)
	if err != nil {
		return nil, err
	}
	model, err := c.Get(ctx, path, true, "")
	if err != nil {
		return nil, err
	}
	if model.Text("type") == "directory" {
		var children []json.RawMessage
		if json.Unmarshal(model["content"], &children) != nil || children == nil || len(children) != 0 {
			return nil, errors.New("仅允许删除空目录")
		}
	}
	if _, err := c.JSON(ctx, http.MethodDelete, contents(path), nil, nil); err != nil {
		return nil, err
	}
	return map[string]any{"path": path, "deleted": true}, nil
}

func (c *Client) Download(ctx context.Context, remote, local string, overwrite bool) (map[string]any, error) {
	if _, err := target(remote); err != nil {
		return nil, err
	}
	model, err := c.Get(ctx, remote, true, "")
	if err != nil {
		return nil, err
	}
	if model.Text("type") == "directory" {
		return nil, errors.New("download 仅支持单文件")
	}
	raw := model["content"]
	var data []byte
	switch model.Text("format") {
	case "base64":
		data, err = base64.StdEncoding.DecodeString(model.Text("content"))
		if len(raw) == 0 || raw[0] != '"' {
			err = errors.New("响应缺少有效的 base64 内容")
		}
	case "json":
		var output bytes.Buffer
		err = json.Indent(&output, raw, "", "  ")
		data = output.Bytes()
	default:
		var content string
		content, err = TextContent(raw)
		data = []byte(content)
	}
	if err != nil {
		return nil, errors.New("无法解码下载内容")
	}
	path, err := filepath.Abs(local)
	if err != nil {
		return nil, err
	}
	if overwrite {
		if info, statErr := os.Stat(filepath.Dir(path)); statErr != nil || !info.IsDir() {
			return nil, errors.New("本地父目录不存在")
		}
		err = localstate.WritePrivate(path, data)
	} else {
		file, openErr := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
		if openErr != nil {
			return nil, openErr
		}
		_, err = file.Write(data)
		err = errors.Join(err, file.Close())
		if err != nil {
			_ = os.Remove(path)
		}
	}
	if err != nil {
		return nil, err
	}
	return map[string]any{"path": remote, "local_path": path, "bytes": len(data)}, nil
}

func TextContent(raw json.RawMessage) (string, error) {
	var line *string
	if json.Unmarshal(raw, &line) == nil && line != nil {
		return *line, nil
	}
	var lines []string
	if json.Unmarshal(raw, &lines) != nil || lines == nil {
		return "", errors.New("Jupyter 未返回文本内容")
	}
	return strings.Join(lines, ""), nil
}
