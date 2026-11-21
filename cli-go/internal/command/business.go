package command

import (
	"bufio"
	"errors"
	"fmt"
	"io"
	"strconv"
	"strings"
	"time"

	"github.com/mossexplore/platform-cli/cli-go/internal/edgelogin"
	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
	"github.com/mossexplore/platform-cli/cli-go/internal/output"
	"github.com/spf13/cobra"
)

func newBusiness(options Options, load loadConfig) *cobra.Command {
	group := &cobra.Command{Use: "business [TENANT_ID]", Short: "管理部门、租户和团队，可直接指定租户 ID", Args: optionalPositional(1)}
	list := &cobra.Command{Use: "list", Short: "显示当前环境可见的部门、租户和团队目录", Args: positional(0)}
	show := &cobra.Command{Use: "show", Short: "显示当前租户或团队上下文", Args: positional(0)}
	use := &cobra.Command{Use: "use", Short: "交互式或通过 ID 选择租户和团队", Args: positional(0)}
	tenant := use.Flags().String("tenant", "", "租户 ID")
	team := use.Flags().String("team", "", "团队 ID 或 key")
	dept := use.Flags().String("department", "", "部门 ID")
	search := use.Flags().String("search", "", "按部门名称或 ID 筛选交互列表")
	refresh := &cobra.Command{Use: "refresh", Short: "打开 Edge 刷新当前环境的业务目录", Args: positional(0)}
	list.RunE = func(cmd *cobra.Command, _ []string) error {
		_, _, _, entry, err := currentBusiness(load, false)
		if err != nil {
			return err
		}
		out, sel := cmd.OutOrStdout(), entry.Selected
		for _, department := range entry.Catalog {
			fmt.Fprintf(out, "部门: %s [%s]\n", labelOrID(department.Name, department.ID), department.ID)
			for _, item := range department.Tenants {
				current := sel.DepartmentID == department.ID && sel.TenantID == item.ID
				marker := ""
				if current && sel.TeamID == "" {
					marker = " *当前"
				}
				fmt.Fprintf(out, "  租户: %s [%s]%s\n", labelOrID(item.Name, item.ID), item.ID, marker)
				for _, slot := range item.Teams {
					marker, availability := "", "可选"
					if current && sel.TeamID == slot.ID {
						marker = " *当前"
					}
					if slot.Status != "available" || slot.BusinessID == "" {
						availability = "禁选: " + slot.Status
					}
					fmt.Fprintf(out, "    团队: %s [%s] (%s)%s\n", labelOrID(slot.Name, slot.ID), slot.ID, availability, marker)
				}
			}
		}
		return nil
	}
	show.RunE = func(cmd *cobra.Command, _ []string) error {
		paths, _, creds, entry, err := currentBusiness(load, false)
		if err != nil {
			return err
		}
		if _, err := paths.SelectedBusiness(creds); err != nil {
			return err
		}
		return printBusiness(cmd, entry)
	}
	selectBusiness := func(cmd *cobra.Command, tenantID string, direct bool) error {
		paths, cfg, creds, entry, err := currentBusiness(load, true)
		if err != nil {
			return err
		}
		department, teamID := *dept, *team
		if cmd.Flags().Changed("search") && (direct || strings.TrimSpace(*search) == "") {
			return usageError{errors.New("--search 须包含关键词且仅用于交互选择")}
		}
		if !direct {
			if cmd.Flags().Changed("team") || cmd.Flags().Changed("department") {
				return usageError{errors.New("请同时通过 --tenant 指定租户")}
			}
			selection, err := selectInteractive(cmd, entry.Catalog, strings.ToLower(strings.TrimSpace(*search)))
			if err != nil {
				return err
			}
			if selection.TenantID == "" {
				_, err := fmt.Fprintln(cmd.ErrOrStderr(), "已取消业务切换")
				return err
			}
			department, tenantID, teamID = selection.DepartmentID, selection.TenantID, selection.TeamID
		}
		entry, err = paths.SelectBusiness(cfg.Profile(), creds, department, tenantID, teamID)
		if err != nil {
			return err
		}
		fmt.Fprintln(cmd.ErrOrStderr(), "[成功] 当前业务上下文已切换：")
		if err := printBusiness(cmd, entry); err != nil {
			return err
		}
		startAutoPing(cmd, paths, cfg, options.Version, true)
		maintainSessionFiles(paths)
		return nil
	}
	use.RunE = func(cmd *cobra.Command, _ []string) error {
		return selectBusiness(cmd, *tenant, cmd.Flags().Changed("tenant"))
	}
	group.RunE = func(cmd *cobra.Command, args []string) error {
		if len(args) == 0 {
			return cmd.Help()
		}
		return selectBusiness(cmd, args[0], true)
	}
	refresh.RunE = func(cmd *cobra.Command, _ []string) error {
		paths, cfg, err := load()
		if err != nil {
			return err
		}
		if _, err := cfg.RequireProfile(); err != nil {
			return err
		}
		if _, err := edgelogin.Run(cmd.Context(), paths, cfg, cmd.ErrOrStderr()); err != nil {
			return err
		}
		_, err = fmt.Fprintln(cmd.ErrOrStderr(), "[成功] 当前环境的业务目录已刷新")
		return err
	}
	group.AddCommand(list, show, use, refresh)
	return group
}

func currentBusiness(load loadConfig, live bool) (localstate.Paths, localstate.Config, localstate.Credentials, localstate.BusinessEntry, error) {
	paths, cfg, err := load()
	if err != nil {
		return paths, cfg, localstate.Credentials{}, localstate.BusinessEntry{}, err
	}
	profile, err := cfg.RequireProfile()
	if err != nil {
		return paths, cfg, localstate.Credentials{}, localstate.BusinessEntry{}, err
	}
	creds, err := paths.CredentialsFor(profile)
	if live {
		creds, err = paths.LoadCredentials(profile, time.Now())
	}
	if err != nil {
		return paths, cfg, creds, localstate.BusinessEntry{}, err
	}
	entry, err := paths.BusinessEntry(creds)
	return paths, cfg, creds, entry, err
}

func printBusiness(cmd *cobra.Command, entry localstate.BusinessEntry) error {
	sel := entry.Selected
	department, tenant, team, dimension := sel.DepartmentID, sel.TenantID, "-", "tenant"
	if sel.TeamID != "" {
		team, dimension = sel.TeamID, "team"
	}
	for _, dept := range entry.Catalog {
		if sel.DepartmentID != dept.ID {
			continue
		}
		department = labelOrID(dept.Name, dept.ID)
		for _, item := range dept.Tenants {
			if sel.TenantID != item.ID {
				continue
			}
			tenant = labelOrID(item.Name, item.ID)
			for _, scope := range item.Teams {
				if sel.TeamID == scope.ID {
					team = labelOrID(scope.Name, scope.ID)
				}
			}
		}
	}
	fields := output.Fields{{Key: "type（选择维度）", Value: dimension}, {Key: "department（部门）", Value: department},
		{Key: "tenant（租户）", Value: tenant}, {Key: "team（团队）", Value: team}, {Key: "businessId", Value: sel.BusinessID}}
	return fields.Table(cmd.OutOrStdout())
}

func selectInteractive(cmd *cobra.Command, catalog []localstate.Department, search string) (localstate.Selection, error) {
	empty := localstate.Selection{}
	departments := []localstate.Department{}
	for _, item := range catalog {
		if strings.Contains(strings.ToLower(item.Name), search) || strings.Contains(strings.ToLower(item.ID), search) {
			departments = append(departments, item)
		}
	}
	input := bufio.NewReader(cmd.InOrStdin())
	out, prompt := cmd.OutOrStdout(), cmd.ErrOrStderr()
	read := func() (string, error) {
		value, err := input.ReadString('\n')
		if err == io.EOF && value == "" {
			return "q", nil
		}
		if err == io.EOF {
			err = nil
		}
		return strings.ToLower(strings.TrimSpace(value)), err
	}
	choose := func(title string, labels []string) (int, error) {
		if len(labels) == 0 {
			return -1, fmt.Errorf("没有可选择的%s", title)
		}
		fmt.Fprintf(prompt, "请选择%s：\n", title)
		for i, label := range labels {
			fmt.Fprintf(out, "  %d. %s\n", i+1, label)
		}
		fmt.Fprint(prompt, "请输入序号（b 返回，q 取消） ")
		text, err := read()
		if err != nil {
			return -1, err
		}
		if text == "q" {
			return -1, nil
		}
		if text == "b" {
			return -2, nil
		}
		position, err := strconv.Atoi(text)
		if err != nil || position < 1 || position > len(labels) {
			return -1, fmt.Errorf("%s序号无效", title)
		}
		return position - 1, nil
	}
	dept, tenant, team := 0, 0, 0
	for stage := 0; ; {
		var selection int
		var err error
		switch stage {
		case 0:
			labels := []string{}
			for _, item := range departments {
				labels = append(labels, labelOrID(item.Name, item.ID))
			}
			selection, err = choose("部门", labels)
			dept = selection
		case 1:
			labels := []string{}
			for _, item := range departments[dept].Tenants {
				labels = append(labels, labelOrID(item.Name, item.ID))
			}
			selection, err = choose("租户", labels)
			tenant = selection
		case 2:
			item := departments[dept].Tenants[tenant]
			labels := []string{labelOrID(item.Name, item.ID) + "（租户级）"}
			for _, slot := range item.Teams {
				label := labelOrID(slot.Name, slot.ID)
				if slot.Status != "available" || slot.BusinessID == "" {
					label += "（禁选）"
				}
				labels = append(labels, label)
			}
			selection, err = choose("团队", labels)
			team = selection
			if team > 0 && (item.Teams[team-1].Status != "available" || item.Teams[team-1].BusinessID == "") {
				fmt.Fprintln(prompt, "该团队不可选择")
				continue
			}
		case 3:
			department := departments[dept]
			item := department.Tenants[tenant]
			scope := ""
			if team > 0 {
				scope = item.Teams[team-1].ID
			}
			fmt.Fprintf(prompt, "请确认选择：部门 %s → 租户 %s → %s\n", department.ID, item.ID, labelOrID(scope, "租户级"))
			fmt.Fprint(prompt, "确认切换？（y 确认，b 返回，q 取消） ")
			answer, err := read()
			if err != nil {
				return empty, err
			}
			switch answer {
			case "y":
				return localstate.Selection{DepartmentID: department.ID, TenantID: item.ID, TeamID: scope}, nil
			case "q":
				return empty, nil
			case "b":
				stage--
			default:
				fmt.Fprintln(prompt, "请输入 y、b 或 q")
			}
			continue
		}
		if err != nil || selection == -1 {
			return empty, err
		}
		if selection == -2 {
			stage = max(0, stage-1)
		} else {
			stage++
		}
	}
}
