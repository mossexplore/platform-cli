package jupyter

import (
	"context"
	_ "embed"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
	"github.com/mossexplore/platform-cli/cli-go/internal/platform"
)

//go:embed exec_worker.py
var execWorker string

type ExecutionOptions struct {
	Kernel, Directory string
	Startup, Timeout  time.Duration
	OutputLimit       int
}

func (c *Client) newKernel(ctx context.Context, cwd, name string) (string, error) {
	if name == "" {
		name = c.Kernel()
	}
	payload, err := c.JSON(ctx, http.MethodPost, "api/kernels", nil, map[string]string{"name": name, "path": cwd})
	if err != nil {
		return "", err
	}
	var model platform.Record
	if json.Unmarshal(payload, &model) != nil || !validSocketID(model.Text("id")) {
		return "", errors.New("Kernel 创建响应缺少有效的 id")
	}
	return model.Text("id"), nil
}

func validSocketID(id string) bool {
	return id != "" && id != "." && id != ".." && !strings.ContainsAny(id, "/\\?%#")
}

func (c *Client) cleanupKernel(ctx context.Context, id string, interrupt bool) []string {
	problems := []string{}
	if id == "" {
		return problems
	}
	ctx, cancel := context.WithTimeout(context.WithoutCancel(ctx), 15*time.Second)
	defer cancel()
	route := "api/kernels/" + url.PathEscape(id)
	if interrupt {
		if _, err := c.JSON(ctx, http.MethodPost, route+"/interrupt", nil, nil); err != nil {
			problems = append(problems, "中断 Kernel 失败")
		}
	}
	if _, err := c.JSON(ctx, http.MethodDelete, route, nil, nil); err != nil {
		problems = append(problems, "释放专用 Kernel 失败，请检查 kernel_id")
	}
	return problems
}

func (c *Client) Execute(ctx context.Context, args []string, opts ExecutionOptions) (map[string]any, error) {
	cwd, err := RemotePath(opts.Directory)
	if err != nil {
		return nil, err
	}
	model, err := c.Get(ctx, cwd, false, "")
	if err != nil {
		return nil, err
	}
	if model.Text("type") != "directory" {
		return nil, errors.New("--cwd 必须是远端已有目录")
	}
	result := map[string]any{
		"id": localstate.NewID(), "status": "STARTING", "exit_code": nil, "stdout": "", "stderr": "",
		"cwd": cwd, "cleanup_errors": []string{}, "remote_state": "not_started",
	}
	kernel, err := c.newKernel(ctx, cwd, opts.Kernel)
	submitted := false
	if err == nil {
		result["kernel_id"] = kernel
		submitted, err = c.executeProcess(ctx, kernel, args, opts, result)
	}
	if err != nil {
		result["status"], result["error"] = "FAILED", err.Error()
		if submitted {
			result["status"], result["remote_state"] = "LOST", "unknown"
		}
		if errors.Is(err, context.Canceled) {
			result["status"], result["error"] = "INTERRUPTED", "本地中断，远端进程状态需确认"
		}
	}
	result["cleanup_errors"] = c.cleanupKernel(ctx, kernel, false)
	return result, nil
}

func (c *Client) executeProcess(ctx context.Context, kernel string, args []string, opts ExecutionOptions, result map[string]any) (bool, error) {
	conn, err := c.socket(ctx, "api/kernels/"+url.PathEscape(kernel)+"/channels")
	if err != nil {
		return false, err
	}
	defer conn.Close()
	channel := kernelChannel{connection: conn, session: localstate.NewID()}
	language, err := channel.ready(ctx, opts.Startup)
	if err != nil {
		return false, err
	}
	if !strings.EqualFold(language, "python") {
		return false, errors.New("exec 需要 Python Kernel，请使用 --kernel 指定")
	}
	argv, err := json.Marshal(args)
	if err != nil {
		return false, err
	}
	const mime = "application/vnd.wiserec.exec+json"
	script := execWorker + fmt.Sprintf("\nimport base64 as _ml_b64, json as _ml_json\nfrom IPython.display import display\ndisplay({%q: run_process(_ml_json.loads(_ml_b64.b64decode(%q)), %g, %d)}, raw=True)\n",
		mime, base64.StdEncoding.EncodeToString(argv), opts.Timeout.Seconds(), opts.OutputLimit)
	if err := c.api.CheckTarget(); err != nil {
		return false, err
	}
	var remote map[string]json.RawMessage
	reply, err := channel.execute(ctx, script, false, time.Now().Add(opts.Timeout+15*time.Second), func(msg kernelMessage) error {
		if msg.Header.Type != "display_data" {
			return nil
		}
		var content struct {
			Data map[string]json.RawMessage `json:"data"`
		}
		if json.Unmarshal(msg.Content, &content) == nil && len(content.Data[mime]) != 0 {
			_ = json.Unmarshal(content.Data[mime], &remote)
		}
		return nil
	})
	if err != nil {
		return true, err
	}
	var done platform.Record
	if json.Unmarshal(reply, &done) != nil || done.Text("status") != "ok" || remote == nil {
		return true, errors.New("远端执行助手失败，进程状态待确认")
	}
	var status string
	if json.Unmarshal(remote["status"], &status) != nil || (status != "SUCCEEDED" && status != "FAILED" && status != "TIMED_OUT") {
		return true, errors.New("远端执行结果状态无效")
	}
	for _, key := range []string{"status", "exit_code", "stdout", "stderr", "truncated", "output_incomplete", "termination", "error"} {
		if value, found := remote[key]; found {
			result[key] = value
		}
	}
	result["remote_state"] = "finished"
	return true, nil
}
