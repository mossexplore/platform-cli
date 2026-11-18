package command

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"path"
	"strings"
	"testing"
)

func TestHistoryLogDownloadReportsStages(t *testing.T) {
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
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				assertBusinessHeader(t, r)
				switch path.Base(r.URL.Path) {
				case "check":
					assertAccess(t, w, r, "ml train history logs download")
				case "queryScheduleTaskList":
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
			args := []string{"train", "history", "logs", "download", "task", "job", "--directory", t.TempDir(), "-o", "json"}
			if tc.name == "plog" {
				args = append(args, "--type", "plog")
			}
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
			fmt.Fprint(w, `{"result":{"code":0,"count":2,"logInfoList":[
				{"taskName":"training","taskId":"task","jobId":"job","businessId":"business-real","status":1,"roleJobId":"first","archiveId":"bad","createUser":"user"},
				{"taskName":"training","taskId":"task","jobId":"job","businessId":"business-real","status":1,"roleJobId":"second","archiveId":"ok","createUser":"user"}]}}`)
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
