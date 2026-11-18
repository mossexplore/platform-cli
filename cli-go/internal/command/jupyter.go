package command

import (
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/url"
	"sort"
	"strings"

	"github.com/mossexplore/platform-cli/cli-go/internal/jupyter"
	"github.com/mossexplore/platform-cli/cli-go/internal/output"
	"github.com/mossexplore/platform-cli/cli-go/internal/platform"
	"github.com/spf13/cobra"
)

func newJupyter(options Options, load loadConfig) *cobra.Command {
	group := &cobra.Command{Use: "jupyter", Short: "Jupyter Notebook 与远程终端"}
	doctor := &cobra.Command{Use: "doctor", Short: "验证 Token、业务上下文、Kernel 与终端接口", Args: positional(0)}
	doctor.Flags().String("studio-id", "", "Web Studio 实例 ID")
	doctor.RunE = withJupyter(options, load, func(cmd *cobra.Command, _ []string, client *jupyter.Client, _ string) error {
		ctx := cmd.Context()
		payload, err := client.JSON(ctx, http.MethodGet, "api/kernelspecs", nil, nil)
		if err != nil {
			return err
		}
		var specs struct {
			Specs map[string]json.RawMessage `json:"kernelspecs"`
		}
		if json.Unmarshal(payload, &specs) != nil || specs.Specs == nil {
			return errors.New("Jupyter kernelspecs 响应无效")
		}
		fmt.Fprintln(cmd.OutOrStdout(), "Kernel 接口：通过")
		items, err := jupyterTerminals(cmd, client)
		if err != nil {
			return err
		}
		names := make([]string, 0, len(specs.Specs))
		for name := range specs.Specs {
			names = append(names, name)
		}
		sort.Strings(names)
		fmt.Fprintln(cmd.OutOrStdout(), "Jupyter HTTP 认证成功；businessid 已携带")
		fmt.Fprintln(cmd.OutOrStdout(), "可用 Kernel："+strings.Join(names, ", "))
		fmt.Fprintf(cmd.OutOrStdout(), "Terminal 接口可用，现有终端 %d 个\n", len(items))
		fmt.Fprintln(cmd.ErrOrStderr(), "WebSocket 通道在实际执行或 attach 时验证。")
		return nil
	})
	terminal := &cobra.Command{Use: "terminal", Short: "远程交互终端"}
	list := &cobra.Command{Use: "list", Short: "列出当前 Jupyter 身份可见的终端", Args: positional(0)}
	list.Flags().String("studio-id", "", "Web Studio 实例 ID")
	list.RunE = withJupyter(options, load, func(cmd *cobra.Command, _ []string, client *jupyter.Client, _ string) error {
		items, err := jupyterTerminals(cmd, client)
		if err != nil {
			return err
		}
		rows := make([][]string, 0, len(items))
		for _, item := range items {
			rows = append(rows, []string{item.Text("name"), dateText(item["last_activity"])})
		}
		return output.Table(cmd.OutOrStdout(), []string{"终端名称", "最后活动（北京时间）"}, rows)
	})
	closeCmd := &cobra.Command{Use: "close NAME", Short: "关闭指定远程终端及其 Shell", Args: positional(1)}
	closeCmd.Flags().String("studio-id", "", "Web Studio 实例 ID")
	closeCmd.RunE = withJupyter(options, load, func(cmd *cobra.Command, args []string, client *jupyter.Client, _ string) error {
		if strings.ContainsAny(args[0], "/\\") || args[0] == "." || args[0] == ".." {
			return errors.New("终端名称无效")
		}
		if _, err := client.JSON(cmd.Context(), http.MethodDelete, "api/terminals/"+url.PathEscape(args[0]), nil, nil); err != nil {
			return err
		}
		_, err := fmt.Fprintln(cmd.ErrOrStderr(), "[成功] 已关闭远程终端："+args[0])
		return err
	})
	terminal.AddCommand(list, closeCmd, newTerminalConnect(options, load, true), newTerminalConnect(options, load, false))
	group.AddCommand(doctor, terminal, newJupyterFiles(options, load), newJupyterExec(options, load), newJupyterNotebook(options, load))
	return group
}

func jupyterTerminals(cmd *cobra.Command, client *jupyter.Client) ([]platform.Record, error) {
	raw, err := client.JSON(cmd.Context(), http.MethodGet, "api/terminals", nil, nil)
	if err != nil {
		return nil, err
	}
	var items []platform.Record
	if json.Unmarshal(raw, &items) != nil || items == nil {
		return nil, errors.New("Jupyter terminals 响应无效")
	}
	for _, item := range items {
		if item.Text("name") == "" {
			return nil, errors.New("Jupyter 终端记录缺少名称")
		}
	}
	return items, nil
}

func withJupyter(options Options, load loadConfig, f func(*cobra.Command, []string, *jupyter.Client, string) error) func(*cobra.Command, []string) error {
	return authorized(options, load, func(cmd *cobra.Command, args []string, api *platform.API, format string) error {
		paths, cfg, err := load()
		if err != nil {
			return err
		}
		if err := api.CheckTarget(); err != nil {
			return err
		}
		id, _ := cmd.Flags().GetString("studio-id")
		client, err := jupyter.Open(cmd.Context(), api, paths, cfg, id)
		if err != nil {
			return err
		}
		defer client.Close()
		return f(cmd, args, client, format)
	})
}
