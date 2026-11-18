package jupyter

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
	"github.com/mossexplore/platform-cli/cli-go/internal/platform"
)

type notebookCell struct {
	record  platform.Record
	outputs []platform.Record
	clear   bool
}

type notebookOutput struct {
	owner *notebookCell
	value platform.Record
}

func (c *Client) RunNotebook(ctx context.Context, source, download string, opts ExecutionOptions, emit func(string)) (map[string]any, error) {
	body, err := os.ReadFile(source)
	if err != nil {
		return nil, err
	}
	var notebook platform.Record
	var version int
	var cells []platform.Record
	if json.Unmarshal(body, &notebook) != nil || json.Unmarshal(notebook["nbformat"], &version) != nil || version != 4 ||
		json.Unmarshal(notebook["cells"], &cells) != nil || cells == nil || notebook.Object("metadata") == nil {
		return nil, errors.New("需要有效的 nbformat 4 Notebook")
	}
	queue := []*notebookCell{}
	for _, cell := range cells {
		switch cell.Text("cell_type") {
		case "code":
			source, err := TextContent(cell["source"])
			if err != nil {
				return nil, errors.New("Notebook 代码单元格缺少有效的 source")
			}
			_ = cell.Put("outputs", []any{})
			_ = cell.Put("execution_count", nil)
			if strings.TrimSpace(source) != "" {
				queue = append(queue, &notebookCell{record: cell, outputs: []platform.Record{}})
			}
		case "raw", "markdown":
		default:
			return nil, errors.New("Notebook 包含不支持的单元格类型")
		}
	}
	metadata := notebook.Object("metadata")
	delete(metadata, "widgets")
	_ = notebook.Put("metadata", metadata)
	syncNotebook := func() error { return notebook.Put("cells", cells) }
	if err := syncNotebook(); err != nil {
		return nil, err
	}
	cwd, err := RemotePath(opts.Directory)
	if err != nil {
		return nil, err
	}
	id := localstate.NewID()
	dir := filepath.Join(download, id)
	if err := os.MkdirAll(download, 0700); err != nil {
		return nil, err
	}
	if err := os.Mkdir(dir, 0700); err != nil {
		return nil, err
	}
	target := filepath.Join(dir, strings.TrimSuffix(filepath.Base(source), filepath.Ext(source))+".executed.ipynb")
	target, err = filepath.Abs(target)
	if err != nil {
		return nil, err
	}
	remote := "ml-runs/" + id
	if cwd != "" {
		remote = cwd + "/" + remote
	}
	result := map[string]any{"id": id, "status": "STARTING", "remote_directory": remote, "notebook": target,
		"started_at": notebookNow(), "completed_cells": 0, "cleanup_errors": []string{}}
	if c.studio != "" {
		result["studio_id"], result["server_url"] = c.studio, c.root.String()
	}
	save := func() error {
		if err := syncNotebook(); err != nil {
			return err
		}
		data, err := json.MarshalIndent(notebook, "", "  ")
		if err != nil {
			return err
		}
		return localstate.WritePrivate(target, data)
	}
	if err := save(); err != nil {
		return nil, err
	}
	emit(fmt.Sprintf("执行 ID：%s\n本地结果：%s\n", id, target))
	kernel, runErr := c.runNotebook(ctx, notebook, queue, cwd, remote, opts, save, emit, result)
	status := "SUCCEEDED"
	if runErr != nil {
		status = "FAILED"
		switch {
		case errors.Is(runErr, context.Canceled):
			status = "INTERRUPTED"
		case errors.Is(runErr, context.DeadlineExceeded):
			status = "TIMED_OUT"
		case errors.Is(runErr, errKernelDisconnected):
			status = "LOST"
		}
		result["error"] = runErr.Error()
	}
	result["status"], result["finished_at"] = status, notebookNow()
	problems := c.cleanupKernel(ctx, kernel, runErr != nil)
	if err := save(); err != nil {
		return nil, err
	}
	finish, stop := context.WithTimeout(context.WithoutCancel(ctx), 15*time.Second)
	defer stop()
	if err := c.saveNotebook(finish, remote+"/executed.ipynb", notebook); err != nil {
		problems = append(problems, "远程结果保存失败，本地结果已保留")
	}
	result["cleanup_errors"] = problems
	summary, err := json.MarshalIndent(result, "", "  ")
	if err != nil {
		return nil, err
	}
	if err := localstate.WritePrivate(filepath.Join(dir, "summary.json"), summary); err != nil {
		return nil, err
	}
	return result, nil
}

func (c *Client) runNotebook(ctx context.Context, notebook platform.Record, queue []*notebookCell, cwd, remote string,
	opts ExecutionOptions, save func() error, emit func(string), result map[string]any) (string, error) {
	parts := strings.Split(remote, "/")
	for i := range parts {
		dir := strings.Join(parts[:i+1], "/")
		if _, err := c.JSON(ctx, http.MethodPut, contents(dir), nil, map[string]string{"type": "directory"}); err != nil {
			return "", err
		}
	}
	if err := c.saveNotebook(ctx, remote+"/input.ipynb", notebook); err != nil {
		return "", err
	}
	if cwd == "" {
		cwd = remote
	}
	id, err := c.newKernel(ctx, cwd, opts.Kernel)
	if err != nil {
		return "", err
	}
	result["kernel_id"] = id
	conn, err := c.socket(ctx, "api/kernels/"+url.PathEscape(id)+"/channels")
	if err != nil {
		return id, err
	}
	defer conn.Close()
	channel := kernelChannel{connection: conn, session: localstate.NewID()}
	if _, err := channel.ready(ctx, opts.Startup); err != nil {
		return id, err
	}
	displays := map[string][]notebookOutput{}
	deadline := time.Now().Add(opts.Timeout)
	result["status"] = "RUNNING"
	for index, cell := range queue {
		if !time.Now().Before(deadline) {
			return id, context.DeadlineExceeded
		}
		if err := ctx.Err(); err != nil {
			return id, err
		}
		if err := c.api.CheckTarget(); err != nil {
			return id, err
		}
		code, _ := TextContent(cell.record["source"])
		emit(fmt.Sprintf("\n正在执行代码单元格 %d/%d\n", index+1, len(queue)))
		reply, err := channel.execute(ctx, code, true, deadline, func(msg kernelMessage) error {
			return notebookEvent(cell, msg, displays, emit)
		})
		var status platform.Record
		_ = json.Unmarshal(reply, &status)
		if counter := status["execution_count"]; len(counter) > 0 {
			cell.record["execution_count"] = counter
		}
		_ = cell.record.Put("outputs", cell.outputs)
		if err != nil {
			return id, err
		}
		if status.Text("status") != "ok" {
			return id, fmt.Errorf("单元格执行失败：%s", status.Text("ename"))
		}
		result["completed_cells"] = index + 1
		if err := save(); err != nil {
			return id, err
		}
	}
	return id, nil
}

func notebookEvent(cell *notebookCell, msg kernelMessage, displays map[string][]notebookOutput, emit func(string)) error {
	clear := func() {
		cell.outputs, cell.clear = []platform.Record{}, false
		for id, matches := range displays {
			filtered := matches[:0]
			for _, item := range matches {
				if item.owner != cell {
					filtered = append(filtered, item)
				}
			}
			displays[id] = filtered
		}
	}
	kind := msg.Header.Type
	switch kind {
	case "clear_output", "stream", "display_data", "execute_result", "error", "update_display_data":
	default:
		return nil
	}
	var content platform.Record
	if json.Unmarshal(msg.Content, &content) != nil || content == nil {
		return errors.New("Kernel 输出结构无效")
	}
	if kind == "clear_output" {
		if string(content["wait"]) == "true" {
			cell.clear = true
		} else {
			clear()
		}
		return nil
	}
	if cell.clear {
		clear()
	}
	displayID := content.Object("transient").Text("display_id")
	if kind == "update_display_data" {
		for _, previous := range displays[displayID] {
			previous.value["data"], previous.value["metadata"] = defaultObject(content["data"]), defaultObject(content["metadata"])
			_ = previous.owner.record.Put("outputs", previous.owner.outputs)
		}
		return nil
	}
	output := platform.Record{}
	_ = output.Put("output_type", kind)
	switch kind {
	case "stream":
		output["name"], output["text"] = content["name"], content["text"]
		text, _ := TextContent(content["text"])
		emit(text)
	case "error":
		output["ename"], output["evalue"], output["traceback"] = content["ename"], content["evalue"], content["traceback"]
		var trace []string
		if json.Unmarshal(content["traceback"], &trace) == nil {
			emit(strings.Join(trace, "\n") + "\n")
		}
	default:
		output["data"], output["metadata"] = defaultObject(content["data"]), defaultObject(content["metadata"])
		if kind == "execute_result" {
			output["execution_count"] = content["execution_count"]
		}
		if text, err := TextContent(content.Object("data")["text/plain"]); err == nil && text != "" {
			emit(text + "\n")
		}
	}
	cell.outputs = append(cell.outputs, output)
	if displayID != "" && (kind == "display_data" || kind == "execute_result") {
		displays[displayID] = append(displays[displayID], notebookOutput{cell, output})
	}
	return nil
}

func defaultObject(raw json.RawMessage) json.RawMessage {
	if len(raw) == 0 {
		return json.RawMessage("{}")
	}
	return raw
}

func (c *Client) saveNotebook(ctx context.Context, path string, notebook platform.Record) error {
	_, err := c.JSON(ctx, http.MethodPut, contents(path), nil,
		map[string]any{"type": "notebook", "format": "json", "content": notebook})
	return err
}

func notebookNow() string {
	return time.Now().In(time.FixedZone("Asia/Shanghai", 8*60*60)).Format("2006-01-02 15:04:05")
}
