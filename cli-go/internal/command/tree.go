package command

import (
	"errors"
	"fmt"
	"io"
	"slices"
	"strings"
	"time"
	"unicode"

	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
	"github.com/spf13/cobra"
)

type branch struct {
	label    string
	children []branch
}

func writeTree(out io.Writer, root *cobra.Command, paths localstate.Paths, cfg localstate.Config, all bool) error {
	profile, err := cfg.RequireProfile()
	if err != nil {
		if !all {
			return errors.New("当前会话尚未绑定环境，请先执行 ml env use <环境名>，或运行 ml tree --all 查看全部命令")
		}
		fmt.Fprintln(out, "当前环境：未绑定（会话模式）")
		if _, err := fmt.Fprintln(out, "ml  WiseRec 命令行工具"); err != nil {
			return err
		}
		return printBranches(out, "", treeBranches(root, "", "", nil, true, false))
	}
	fmt.Fprintf(out, "当前环境：%s · 管理台类型：%s\n", profile.Name, profile.PlatformType)
	creds, err := paths.LoadCredentials(profile, time.Now())
	showAllBusiness := err == nil && creds.HasAdminFlags() && creds.CanQueryAllBusiness()
	if showAllBusiness {
		fmt.Fprintf(out, "当前账号权限：%s · 标记“支持 -A”的列表命令可使用 --all-business / -A 查全租户\n", creds.AdminRoleLabel())
	}
	if !all {
		fmt.Fprintln(out, "仅展示当前环境支持的命令；查看全部命令：ml tree --all")
	}
	rules := append([]string(nil), profile.Policy.Deny...)
	if !cfg.Access.Active() || cfg.Access.URL == "" {
		fmt.Fprintln(out, "Go 业务命令要求在线权限校验")
	} else if policy := paths.Policy(cfg.Access, profile); policy != nil {
		rules = append(rules, policy.Deny...)
	} else {
		fmt.Fprintln(out, "服务端环境策略尚未同步，执行时将实时检查")
	}
	if _, err := fmt.Fprintln(out, "ml  WiseRec 命令行工具"); err != nil {
		return err
	}
	return printBranches(out, "", treeBranches(root, "", profile.PlatformType, rules, all, showAllBusiness))
}

func treeBranches(cmd *cobra.Command, path, platformType string, rules []string, all, showAllBusiness bool) []branch {
	var branches []branch
	commands := cmd.Commands()
	if path == "" {
		order := map[string]int{"kb": -1, "context": 0, "login": 1, "logout": 2, "tree": 3, "history": 4, "auth": 5, "access": 6, "business": 7, "env": 8, "user": 9, "mtp": 11, "offline": 12, "train": 13, "sample-task": 14, "model": 15, "resource": 16, "deployment": 17, "algorithm": 18, "dataset": 19, "service": 20, "featureset": 21, "feature-task": 22, "quality": 23, "jupyter": 24, "webstudio": 25}
		commands = slices.Clone(commands)
		slices.SortStableFunc(commands, func(left, right *cobra.Command) int {
			return order[left.Name()] - order[right.Name()]
		})
	}
	for _, child := range commands {
		if child.Name() == "help" || child.Hidden || !child.IsAvailableCommand() {
			continue
		}
		childPath := strings.TrimSpace(path + " " + child.Name())
		blocked := localstate.Denied(childPath, rules)
		unsupported := platformType == "mlops" && wiseRecOnly(child)
		if (blocked || unsupported) && !all {
			continue
		}
		children := treeBranches(child, childPath, platformType, rules, all, showAllBusiness)
		if !child.Runnable() && len(children) == 0 {
			continue
		}
		label := child.Name() + "  " + treeSummary(child.Short)
		if unsupported {
			label += "  [不支持]"
		} else if blocked {
			label += "  [当前环境禁用]"
		} else if showAllBusiness && child.Flags().Lookup(allBusinessFlag) != nil {
			label += "  支持 -A"
		}
		branches = append(branches, branch{label: label, children: children})
	}
	return branches
}

func printBranches(out io.Writer, indent string, branches []branch) error {
	for index, node := range branches {
		stem, next := "├── ", "│   "
		if index == len(branches)-1 {
			stem, next = "└── ", "    "
		}
		if _, err := fmt.Fprintln(out, indent+stem+node.label); err != nil {
			return err
		}
		if err := printBranches(out, indent+next, node.children); err != nil {
			return err
		}
	}
	return nil
}

func treeSummary(summary string) string {
	summary, _, _ = strings.Cut(summary, "；")
	summary = strings.TrimSpace(summary)
	for summary != "" {
		last := []rune(summary)
		closing := last[len(last)-1]
		if !unicode.IsPunct(closing) {
			break
		}
		end := string(last[:len(last)-1])
		opening := map[rune]string{'）': "（", ')': "("}[closing]
		if opening != "" {
			if index := strings.LastIndex(end, opening); index >= 0 {
				summary = strings.TrimSpace(strings.TrimRight(end[:index], " ") + "，" + end[index+len(opening):])
				continue
			}
		}
		summary = strings.TrimSpace(end)
	}
	return summary
}
