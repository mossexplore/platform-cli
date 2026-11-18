package jupyter

import (
	"context"
	"encoding/binary"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/gorilla/websocket"
	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
)

func (c *Client) socket(ctx context.Context, endpoint string) (*websocket.Conn, error) {
	address := *c.root
	relative, err := url.Parse(endpoint)
	if err != nil || relative.IsAbs() || relative.Host != "" || strings.HasPrefix(relative.Path, "/") ||
		strings.Contains(relative.Path, "..") || strings.Contains(relative.Path, "\\") {
		return nil, errors.New("Jupyter WebSocket 路径无效")
	}
	address.Path += relative.Path
	headers := c.api.RequestMetadata()
	for _, cookie := range c.http.Jar.Cookies(&address) {
		value := cookie.String()
		if previous := headers.Get("Cookie"); previous != "" {
			value = previous + "; " + value
		}
		headers.Set("Cookie", value)
	}
	if c.token != "" {
		headers.Set("Authorization", "token "+c.token)
	}
	headers.Set("Origin", c.root.Scheme+"://"+c.root.Host)
	if address.Scheme == "https" {
		address.Scheme = "wss"
	} else {
		address.Scheme = "ws"
	}
	transport := c.http.Transport.(*http.Transport)
	dial := websocket.Dialer{HandshakeTimeout: c.http.Timeout, TLSClientConfig: transport.TLSClientConfig}
	conn, response, err := dial.DialContext(ctx, address.String(), headers)
	if err != nil {
		if response != nil {
			defer response.Body.Close()
			body, _ := io.ReadAll(io.LimitReader(response.Body, 1<<20))
			if policyErr := c.api.CheckVersion(body); policyErr != nil {
				return nil, policyErr
			}
		}
		if ctx.Err() != nil {
			return nil, ctx.Err()
		}
		return nil, errors.New("Jupyter WebSocket 连接失败，请检查 Token、权限及代理 Upgrade 配置")
	}
	conn.SetReadLimit(32 << 20)
	return conn, nil
}

type kernelChannel struct {
	connection *websocket.Conn
	session    string
}

type kernelMessage struct {
	Header struct {
		Type string `json:"msg_type"`
	} `json:"header"`
	Parent struct {
		ID string `json:"msg_id"`
	} `json:"parent_header"`
	Channel string          `json:"channel"`
	Content json.RawMessage `json:"content"`
}

var errKernelDisconnected = errors.New("Kernel 连接中断，执行结果待确认")

func decodeKernel(kind int, data []byte) (kernelMessage, error) {
	var msg kernelMessage
	if kind == websocket.BinaryMessage {
		if len(data) < 8 {
			return msg, errors.New("Kernel 返回无效二进制消息")
		}
		count := uint64(binary.BigEndian.Uint32(data[:4]))
		extra := 4 * (count + 1)
		if count < 1 || extra > uint64(len(data)) {
			return msg, errors.New("Kernel 返回无效二进制消息")
		}
		start, end := uint64(binary.BigEndian.Uint32(data[4:8])), uint64(len(data))
		if count > 1 {
			end = uint64(binary.BigEndian.Uint32(data[8:12]))
		}
		if start < extra || start > end || end > uint64(len(data)) {
			return msg, errors.New("Kernel 返回无效消息偏移")
		}
		data = data[start:end]
	}
	if err := json.Unmarshal(data, &msg); err != nil {
		return msg, errors.New("Kernel 返回无效 JSON 消息")
	}
	return msg, nil
}

func (k kernelChannel) send(kind string, content any) (string, error) {
	id := localstate.NewID()
	data := map[string]any{
		"header": map[string]string{"msg_id": id, "session": k.session, "username": "ml",
			"msg_type": kind, "version": "5.3", "date": time.Now().UTC().Format(time.RFC3339Nano)},
		"parent_header": map[string]any{}, "metadata": map[string]any{}, "content": content, "channel": "shell", "buffers": []any{},
	}
	if err := k.connection.WriteJSON(data); err != nil {
		return "", errKernelDisconnected
	}
	return id, nil
}

func (k kernelChannel) read(ctx context.Context, id string, until time.Time, consume func(kernelMessage) (bool, error)) error {
	if deadline, ok := ctx.Deadline(); ok && deadline.Before(until) {
		until = deadline
	}
	if err := k.connection.SetReadDeadline(until); err != nil {
		return errKernelDisconnected
	}
	stop := context.AfterFunc(ctx, func() { _ = k.connection.Close() })
	defer stop()
	for {
		kind, raw, err := k.connection.ReadMessage()
		if err != nil {
			if ctx.Err() != nil {
				return ctx.Err()
			}
			if !time.Now().Before(until) {
				return context.DeadlineExceeded
			}
			return errKernelDisconnected
		}
		event, err := decodeKernel(kind, raw)
		if err != nil {
			return err
		}
		if event.Parent.ID != id {
			continue
		}
		done, err := consume(event)
		if err != nil || done {
			return err
		}
	}
}

func (k kernelChannel) ready(ctx context.Context, startup time.Duration) (string, error) {
	id, err := k.send("kernel_info_request", map[string]any{})
	if err != nil {
		return "", err
	}
	language := ""
	err = k.read(ctx, id, time.Now().Add(startup), func(event kernelMessage) (bool, error) {
		if event.Header.Type != "kernel_info_reply" {
			return false, nil
		}
		var info struct {
			Language struct{ Name string } `json:"language_info"`
		}
		if json.Unmarshal(event.Content, &info) != nil {
			return false, errors.New("Kernel 就绪响应无效")
		}
		language = info.Language.Name
		return true, nil
	})
	return language, err
}

func (k kernelChannel) execute(ctx context.Context, code string, history bool, until time.Time, stream func(kernelMessage) error) (json.RawMessage, error) {
	id, err := k.send("execute_request", map[string]any{
		"code": code, "silent": false, "store_history": history, "user_expressions": map[string]any{},
		"allow_stdin": false, "stop_on_error": true,
	})
	if err != nil {
		return nil, err
	}
	var reply json.RawMessage
	idle := false
	err = k.read(ctx, id, until, func(event kernelMessage) (bool, error) {
		if event.Header.Type == "execute_reply" && event.Channel == "shell" {
			reply = event.Content
		} else if event.Header.Type == "status" {
			var state struct {
				State string `json:"execution_state"`
			}
			if json.Unmarshal(event.Content, &state) != nil {
				return false, errors.New("Kernel 状态消息无效")
			}
			idle = idle || state.State == "idle"
		} else if event.Channel == "iopub" {
			if err := stream(event); err != nil {
				return false, err
			}
		}
		return idle && len(reply) != 0, nil
	})
	return reply, err
}
