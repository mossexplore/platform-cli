package command

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path"
	"path/filepath"
	"strings"
	"testing"

	"github.com/mossexplore/platform-cli/cli-go/internal/platform"
)

func TestHistoryLogRoleSelectionTable(t *testing.T) {
	var roles []platform.Record
	if err := json.Unmarshal([]byte(`[
		{"roleJobId":"11111111-1111-1111-1111-111111111111","roleType":"chief","algorithmName":"Ranker","status":"RUNNING","infraSize":2,"cpuSize":16,"gpuSize":0,"memorySize":"32Gi","hostIp":"10.0.0.1","createTime":1788850476000},
		{"roleJobId":"22222222-2222-2222-2222-222222222222","roleType":"worker","createTime":"2026-09-08T06:54:37.123+00:00"}
	]`), &roles); err != nil {
		t.Fatal(err)
	}
	t.Setenv("COLUMNS", "160")
	var out bytes.Buffer
	if err := renderTrainHistoryLogRoles(&out, roles); err != nil {
		t.Fatal(err)
	}
	lines := strings.Split(out.String(), "\n")
	want := []string{
		"编号|roleJobId|名称|算法名称|状态|节点数|CPU|GPU|内存|执行节点|开始时间",
		"1|11111111-1111-1111-1111-111111111111|chief|Ranker|RUNNING|2|16|0|32Gi|10.0.0.1|2026-09-08 14:54:36",
		"2|22222222-2222-2222-2222-222222222222|worker|-|-|-|-|-|-|-|2026-09-08 14:54:37",
	}
	for i, lineIndex := range []int{1, 3, 4} {
		cells := strings.FieldsFunc(lines[lineIndex], func(r rune) bool { return r == '┃' || r == '│' })
		for j := range cells {
			cells[j] = strings.TrimSpace(cells[j])
		}
		if got := strings.Join(cells, "|"); got != want[i] {
			t.Errorf("line %d = %q, want %q", lineIndex, got, want[i])
		}
	}
	t.Setenv("COLUMNS", "80")
	out.Reset()
	if err := renderTrainHistoryLogRoles(&out, roles); err != nil {
		t.Fatal(err)
	}
	for _, text := range []string{"11111111-1111-1111-1111-111111111111", "2026-09-08 14:54:36"} {
		if !strings.Contains(out.String(), text) {
			t.Errorf("narrow output split %q:\n%s", text, out.String())
		}
	}
}

func TestHistoryLogDownloadWithoutDistributedRoles(t *testing.T) {
	t.Setenv("ML_HISTORY", "0")
	for _, roleInfo := range []string{"null", "[]"} {
		t.Run(roleInfo, func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				switch path.Base(r.URL.Path) {
				case "check":
					assertAccess(t, w, r, "ml train history logs download")
				case "queryScheduleTaskList":
					fmt.Fprintf(w, `{"result":{"code":0,"count":1,"jobs":[{"jobId":"job","jobType":"dps-train","roleJobInfo":%s}]}}`, roleInfo)
				default:
					t.Errorf("unexpected request %s", r.URL.Path)
					w.WriteHeader(http.StatusNotFound)
				}
			}))
			defer server.Close()
			paths := fixtureConfig(t, t.TempDir(), server.URL, server.URL, false, "mlops", "")
			saveState(t, paths, server.URL)
			for _, options := range [][]string{nil, {"-o", "json", "--role-job-id", "role"}} {
				args := append([]string{"train", "history", "logs", "download", "task", "job"}, options...)
				code, out, stderr := run(t, paths, args...)
				if code != 1 || out != "" || !strings.Contains(stderr, "阶段「选择日志角色」失败：该job无分布式角色，无日志可下载") ||
					strings.Contains(stderr, "输入日志编号") {
					t.Fatalf("options %v: code=%d stdout=%q stderr=%q", options, code, out, stderr)
				}
			}
		})
	}
}

func TestHistoryLogDownloadReportsStages(t *testing.T) {
	t.Setenv("ML_HISTORY", "0")
	storage := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		fmt.Fprint(w, "test log")
	}))
	defer storage.Close()

	for _, tc := range []struct {
		name, status, failedStage, address string
	}{
		{name: "normal", status: "downloaded", address: storage.URL + "?signature=fixture-secret"},
		{name: "plog", status: "downloaded", address: storage.URL + "?signature=fixture-secret"},
		{name: "invalid URL", status: "failed", failedStage: "validate_download_url", address: "http://invalid.example/?signature=fixture-secret"},
		{name: "archive", status: "not_ready", failedStage: "archive_log"},
		{name: "log check fails", status: "failed", failedStage: "check_log"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			directory := filepath.Join(t.TempDir(), "saved logs")
			if err := os.Mkdir(directory, 0700); err != nil {
				t.Fatal(err)
			}
			args := []string{"train", "history", "logs", "download", "task", "job", "--directory", directory, "-o", "json"}
			audit := "ml train history logs download task job --directory " + quoteCommandArg(directory) + " -o json"
			if tc.name == "plog" {
				args = append(args, "--type=plog")
				audit += " --type=plog"
			}
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				assertBusinessHeader(t, r)
				switch path.Base(r.URL.Path) {
				case "check":
					body := assertAccess(t, w, r, "ml train history logs download")
					if body["full_command"] != audit {
						t.Errorf("incorrect audit command: %v", body["full_command"])
					}
				case "queryScheduleTaskList":
					if body := readRequest(t, r); body["latestFlag"] != "all" {
						fmt.Fprint(w, `{"result":{"code":0,"count":1,"jobs":[{"taskId":"task","jobId":"latest-job"}]}}`)
						return
					}
					fmt.Fprint(w, `{"result":{"code":0,"count":1,"jobs":[{"taskId":"task","jobId":"job","sysParam":"{\"plogUploadSuccess\":\"1\"}"}]}}`)
				case "queryJobLogIsExist":
					if tc.name == "plog" {
						t.Error("plog should skip the ordinary log check")
					}
					if tc.name == "log check fails" {
						fmt.Fprint(w, `{"result":{"code":1}}`)
					} else {
						fmt.Fprintf(w, `{"result":{"code":0,"isExistLog":%t}}`, tc.name != "archive")
					}
				case "downloadLogUrl":
					fmt.Fprintf(w, `{"result":{"code":0,"url":%q}}`, tc.address)
				case "downloadPlog":
					fmt.Fprintf(w, `{"result":{"code":0,"plogUrl":%q}}`, tc.address)
				case "manualArchiveLog":
					fmt.Fprint(w, `{"result":{"code":0}}`)
				default:
					t.Errorf("unexpected request %s", r.URL.Path)
					w.WriteHeader(http.StatusNotFound)
				}
			}))
			defer server.Close()
			paths := fixtureConfig(t, t.TempDir(), server.URL, server.URL, false, "mlops", "")
			saveState(t, paths, server.URL)
			code, out, stderr := run(t, paths, args...)
			var result struct {
				Status, Stage, Error string
			}
			if err := json.Unmarshal([]byte(out), &result); err != nil {
				t.Fatalf("invalid JSON output, %v: %s\n%s", err, out, stderr)
			}
			if result.Status != tc.status || result.Stage != tc.failedStage || (code == 0) != (tc.status == "downloaded") {
				t.Fatalf("unexpected result (%d): %s\n%s", code, out, stderr)
			}
			if strings.Contains(out+stderr, "fixture-secret") {
				t.Fatal("signed URL reached command output")
			}
			steps := []string{"开始查询执行记录", "开始校验 1 条待下载日志的信息"}
			switch tc.name {
			case "normal":
				steps = append(steps, "开始查询日志是否存在", "日志存在，开始获取日志下载地址", "开始校验下载地址", "开始下载 日志", "日志下载完成")
			case "plog":
				steps = append(steps, "开始获取 plog 下载地址", "开始校验下载地址", "开始下载 plog 日志", "plog 日志下载完成")
			case "archive":
				steps = append(steps, "开始查询日志是否存在", "日志未就绪，开始手动归档", "手动归档中")
			case "invalid URL":
				steps = append(steps, "开始查询日志是否存在", "日志存在，开始获取日志下载地址", "开始校验下载地址")
			case "log check fails":
				steps = append(steps, "开始查询日志是否存在")
			}
			expectDownloadSteps(t, stderr, steps...)
			if result.Error != "" && !strings.Contains(stderr, result.Error) {
				t.Fatalf("failure summary missing from stderr: %s\n%s", out, stderr)
			}
		})
	}
}

func TestInstanceLogDownloadReportsBatchSteps(t *testing.T) {
	t.Setenv("COLUMNS", "80")
	const roleID = "00000000-0000-4000-8000-000000000001"
	storage := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		fmt.Fprint(w, "test log")
	}))
	defer storage.Close()
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		assertBusinessHeader(t, r)
		switch path.Base(r.URL.Path) {
		case "check":
			assertAccess(t, w, r, "ml train instance logs download")
		case "queryList":
			fmt.Fprint(w, `{"result":{"code":0,"count":1,"taskInfos":[{"taskId":"task","taskType":"dps-train","businessId":"business-real"}]}}`)
		case "queryJobInstanceByTaskId":
			fmt.Fprint(w, `{"result":{"code":0,"count":1,"jobs":[{"taskName":"training","taskId":"task","jobId":"job","businessId":"business-real"}]}}`)
		case "getRunJobLogArchiveList":
			fmt.Fprintf(w, `{"result":{"code":0,"count":4,"logInfoList":[
				{"taskName":"training","taskId":"task","jobId":"job","businessId":"business-real","status":1,"roleJobId":"first","archiveId":"bad","createUser":"user"},
				{"taskName":"training","taskId":"task","jobId":"job","businessId":"business-real","status":1,"roleJobId":%q,"archiveId":"ok","createUser":"user","roleType":"worker","createTime":1788850476000,"updateTime":"2026-09-08T07:00:00.123+00:00"},
				{"taskName":"training","taskId":"task","jobId":"job","businessId":"business-real","status":0,"roleJobId":"third"},
				{"taskName":"training","taskId":"task","jobId":"job","businessId":"business-real","status":2,"roleJobId":"fourth","statusReason":"写入失败"}]}}`, roleID)
		case "getRunningJobLogUrl":
			body := readRequest(t, r)
			address := "http://invalid.example"
			if data, ok := body["data"].(map[string]any); ok && data["archiveId"] == "ok" {
				address = storage.URL
			}
			fmt.Fprintf(w, `{"result":{"code":0,"downloadUrl":%q}}`, address)
		default:
			t.Errorf("unexpected request %s", r.URL.Path)
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()
	paths := fixtureConfig(t, t.TempDir(), server.URL, server.URL, false, "mlops", "")
	saveState(t, paths, server.URL)
	code, out, stderr := run(t, paths, "train", "instance", "logs", "download", "task", "job", "--select", "all", "--directory", t.TempDir(), "-o", "json")
	var result struct {
		Failed, Succeeded int
		Items             []struct{ Status, Stage string }
	}
	if err := json.Unmarshal([]byte(out), &result); err != nil {
		t.Fatalf("invalid JSON output, %v: %s\n%s", err, out, stderr)
	}
	if code != 1 || result.Failed != 1 || result.Succeeded != 1 || len(result.Items) != 2 ||
		result.Items[0].Stage != "validate_download_url" || result.Items[1].Status != "downloaded" {
		t.Fatalf("unexpected batch result (%d): %s\n%s", code, out, stderr)
	}
	expectDownloadSteps(t, stderr, "开始查询执行实例", "请求归档并查询归档日志", "已获取归档记录",
		"开始处理第 1/2 条日志", "开始获取编号 1 的日志下载地址", "开始校验下载地址",
		"开始处理第 2/2 条日志", "开始获取编号 2 的日志下载地址", "开始校验下载地址", "开始下载 日志", "日志下载完成")

	agentDir := t.TempDir()
	code, out, agentStderr := run(t, paths, "train", "instance", "logs", "download", "task", "job", "--select", "all", "--directory", agentDir, "--agent")
	if code != 1 || strings.Count(out, "\n") != 1 || json.Unmarshal([]byte(out), &result) != nil ||
		result.Failed != 1 || result.Succeeded != 1 || len(result.Items) != 2 || !strings.Contains(agentStderr, "日志下载完成") {
		t.Fatal(code, out, agentStderr)
	}
	saved, err := os.ReadDir(agentDir)
	if err != nil || len(saved) != 1 {
		t.Fatal(saved, err)
	}
	content, err := os.ReadFile(filepath.Join(agentDir, saved[0].Name()))
	if err != nil || string(content) != "test log" {
		t.Fatal(string(content), err)
	}

	var table []string
	for _, line := range strings.Split(stderr, "\n") {
		cells := strings.FieldsFunc(line, func(r rune) bool { return r == '┃' || r == '│' })
		if len(cells) == 10 {
			for i := range cells {
				cells[i] = strings.TrimSpace(cells[i])
			}
			table = append(table, strings.Join(cells, "|"))
		}
	}
	wantTable := []string{
		"编号|任务名称|jobId|roleJobId|节点名称|状态|失败原因|开始时间|结束时间|是否可以下载",
		"1|training|job|first|-|归档成功|-|-|-|是",
		"2|training|job|" + roleID + "|worker|归档成功|-|2026-09-08 14:54:36|2026-09-08 15:00:00|是",
		"3|training|job|third|-|归档中|-|-|-|否",
		"4|training|job|fourth|-|归档失败|写入失败|-|-|否",
	}
	if strings.Join(table, "\n") != strings.Join(wantTable, "\n") {
		t.Fatalf("unexpected archive table:\n%s", stderr)
	}
	for _, number := range []string{"3", "4"} {
		code, _, stderr := run(t, paths, "train", "instance", "logs", "download", "task", "job", "--select", number, "--directory", t.TempDir())
		if code == 0 || !strings.Contains(stderr, "编号 "+number+" 尚不可下载") {
			t.Fatalf("unavailable archive %s was not rejected (%d): %s", number, code, stderr)
		}
	}
}

func expectDownloadSteps(t *testing.T, output string, steps ...string) {
	t.Helper()
	for index, step := range steps {
		line := fmt.Sprintf("[%d] %s", index+1, step)
		_, remaining, found := strings.Cut(output, line)
		if !found {
			t.Fatalf("missing step %q in %s", line, output)
		}
		output = remaining
	}
}
