package jupyter

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/url"
	"os"
	"time"

	"github.com/gorilla/websocket"
	"github.com/mossexplore/platform-cli/cli-go/internal/platform"
	"golang.org/x/term"
)

func (c *Client) CreateTerminal(ctx context.Context) (string, error) {
	raw, err := c.JSON(ctx, http.MethodPost, "api/terminals", nil, map[string]any{})
	if err != nil {
		return "", err
	}
	var created platform.Record
	if json.Unmarshal(raw, &created) != nil || !validSocketID(created.Text("name")) {
		return "", errors.New("终端创建响应缺少有效的名称")
	}
	return created.Text("name"), nil
}

func (c *Client) Attach(ctx context.Context, name string, in, out *os.File) error {
	if !validSocketID(name) {
		return errors.New("终端名称无效")
	}
	connection, err := c.socket(ctx, "terminals/websocket/"+url.PathEscape(name))
	if err != nil {
		return err
	}
	defer connection.Close()
	fd := int(in.Fd())
	state, err := term.MakeRaw(fd)
	if err != nil {
		return errors.New("无法切换终端为交互模式")
	}
	defer term.Restore(fd, state)
	ctx, cancel := context.WithCancel(ctx)
	defer cancel()
	write := func(value []any) error {
		if err := connection.SetWriteDeadline(time.Now().Add(10 * time.Second)); err != nil {
			return err
		}
		return connection.WriteJSON(value)
	}
	receive := make(chan error, 1)
	go func() {
		for {
			_, payload, err := connection.ReadMessage()
			if err != nil {
				if websocket.IsCloseError(err, websocket.CloseNormalClosure, websocket.CloseGoingAway) {
					receive <- nil
				} else {
					receive <- errors.New("终端连接中断，可用 terminal list 检查")
				}
				return
			}
			var message []json.RawMessage
			if json.Unmarshal(payload, &message) != nil || len(message) < 1 {
				receive <- errors.New("远程终端响应无效")
				return
			}
			var kind string
			_ = json.Unmarshal(message[0], &kind)
			if kind == "disconnect" {
				receive <- nil
				return
			}
			if kind == "stdout" && len(message) > 1 {
				var value string
				if json.Unmarshal(message[1], &value) == nil {
					if _, err := io.WriteString(out, value); err != nil {
						receive <- err
						return
					}
				}
			}
		}
	}()
	input := make(chan rune)
	go func() {
		defer close(input)
		reader := bufio.NewReader(in)
		for {
			value, _, err := reader.ReadRune()
			if err != nil {
				return
			}
			select {
			case input <- value:
			case <-ctx.Done():
				return
			}
			if value == 0x1d {
				return
			}
		}
	}()
	timer := time.NewTicker(250 * time.Millisecond)
	defer timer.Stop()
	width, height := 0, 0
	for {
		columns, rows, err := term.GetSize(int(out.Fd()))
		if err != nil || columns <= 0 || rows <= 0 {
			columns, rows = 80, 24
		}
		if columns != width || rows != height {
			if err := write([]any{"set_size", rows, columns, 0, 0}); err != nil {
				return errors.New("远程终端连接中断")
			}
			width, height = columns, rows
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		case err := <-receive:
			return err
		case value, ok := <-input:
			if !ok || value == 0x1d {
				return nil
			}
			if err := write([]any{"stdin", string(value)}); err != nil {
				return errors.New("远程终端连接中断")
			}
		case <-timer.C:
		}
	}
}
