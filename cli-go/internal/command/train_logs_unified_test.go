package command

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path"
	"strings"
	"testing"
	"testing/synctest"
	"time"
	"unicode"

	"github.com/mossexplore/platform-cli/cli-go/internal/platform"
	"github.com/spf13/cobra"
)

func TestUnifiedTrainLogRoutes(t *testing.T) {
	t.Setenv("ML_HISTORY", "0")
	t.Setenv("COLUMNS", "350")
	for _, tc := range []struct {
		name, manager, source, status string
		flags                         []string
		code, archives, links, files  int
	}{
		{"explicit whole job", "mlops", "running", "partial", []string{"job", "--retry"}, 1, 1, 3, 3},
		{"no automatic retry", "wiserec", "running", "partial", []string{"job", "--all"}, 1, 1, 1, 1},
		{"one role", "mlops", "running", "failed", []string{"job", "--role-job-id", "failed"}, 1, 1, 0, 0},
		{"changed business", "mlops", "running", "failed", []string{"job", "--retry"}, 1, 0, 0, 0},
		{"denied archive", "wiserec", "running", "failed", []string{"job", "--retry"}, 1, 1, 0, 0},
		{"missing selection", "mlops", "running", "", []string{"job"}, 2, 1, 0, 0},
		{"history table", "mlops", "history", "not_ready", []string{"job", "--no-wait"}, 0, 0, 0, 0},
		{"history roles", "mlops", "history", "", []string{"job"}, 2, 0, 0, 0},
		{"latest history", "mlops", "history", "not_ready", []string{"--no-wait"}, 0, 0, 0, 0},
		{"transition", "wiserec", "history", "not_ready", []string{"job", "--wait-timeout", "0"}, 0, 0, 0, 0},
		{"plog", "mlops", "history", "succeeded", []string{"job", "--type", "plog"}, 0, 0, 1, 1},
		{"history retry", "wiserec", "history", "failed", []string{"job", "--retry"}, 1, 0, 0, 0},
	} {
		t.Run(tc.name, func(t *testing.T) {
			dir := t.TempDir() + "/log files"
			if err := os.Mkdir(dir, 0700); err != nil {
				t.Fatal(err)
			}
			archiveCount, linkCount, instances, historyPages := 0, 0, 0, 0
			storage := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				for _, h := range []string{"businessid", "Cookie", "Authorization", "csrftoken"} {
					if r.Header.Get(h) != "" {
						t.Errorf("storage received %s", h)
					}
				}
				fmt.Fprint(w, "log file")
			}))
			defer storage.Close()
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				assertBusinessHeader(t, r)
				switch path.Base(r.URL.Path) {
				case "check":
					assertAccess(t, w, r, "ml train logs download")
				case "list", "queryList":
					tasks := `"count":1,"taskInfos":[{"taskId":"task","taskType":"dps-train","businessId":"business-real"}]`
					if tc.manager == "wiserec" {
						tasks = `"data":{` + tasks + "}"
					}
					fmt.Fprintf(w, `{"result":{"code":0,%s}}`, tasks)
				case "queryJobInstanceByTaskId":
					instances++
					if tc.name == "changed business" && instances == 2 {
						fmt.Fprint(w, `{"result":{"code":0,"count":1,"jobs":[{"jobId":"job","taskId":"task","taskName":"task","businessId":"other"}]}}`)
						return
					}
					if tc.source == "running" || tc.name == "transition" && instances == 1 {
						fmt.Fprint(w, `{"result":{"code":0,"count":1,"jobs":[{"jobId":"job","taskId":"task","taskName":"task","businessId":"business-real"}]}}`)
					} else {
						fmt.Fprint(w, `{"result":{"code":0,"count":0,"jobs":[]}}`)
					}
				case "getRunJobLogArchiveList":
					archiveCount++
					data := readRequest(t, r)["data"].(map[string]any)
					if r.Method != "POST" || len(data) != 3 || data["taskId"] != "task" || data["jobId"] != "job" || data["businessId"] != "business-real" {
						t.Errorf("unexpected archive scope: %v", data)
					}
					if tc.name == "denied archive" {
						fmt.Fprint(w, `{"result":{"code":1}}`)
						return
					}
					entries := []map[string]any{}
					for n, role := range []string{"ready", "failed", "failed", "pending"} {
						entries = append(entries, map[string]any{"taskId": "task", "taskName": "task", "jobId": "job", "businessId": "business-real", "roleJobId": role, "archiveId": fmt.Sprint(n), "status": []int{1, 2, 2, 0}[n], "createTime": 100 + n, "createUser": "user", "statusReason": "disk full"})
					}
					json.NewEncoder(w).Encode(map[string]any{"result": map[string]any{"code": 0, "count": 4, "logInfoList": entries}})
				case "getRunningJobLogUrl":
					id := readRequest(t, r)["data"].(map[string]any)["archiveId"]
					if id == "3" || tc.name != "explicit whole job" && id != "0" {
						t.Errorf("unexpected archive %v", id)
					}
					linkCount++
					fmt.Fprintf(w, `{"result":{"code":0,"downloadUrl":%q}}`, storage.URL)
				case "queryScheduleTaskList":
					if tc.name == "history retry" || tc.source == "running" {
						t.Error("unexpected switch to history")
					}
					historyPages++
					if tc.name == "history roles" {
						fmt.Fprint(w, `{"result":{"code":0,"count":1,"jobs":[{"jobId":"job","jobType":"dps-train","roleJobInfo":[{"roleJobId":"server-id","roleType":"server"},{"roleJobId":"worker-id","roleType":"worker"}]}]}}`)
						return
					}
					if tc.name == "latest history" {
						id, stamp := "old", 1
						if historyPages == 2 {
							id, stamp = "job", 2
						}
						fmt.Fprintf(w, `{"result":{"code":0,"count":2,"jobs":[{"jobId":%q,"statusTime":%d}]}}`, id, stamp)
					} else {
						fmt.Fprint(w, `{"result":{"code":0,"count":1,"jobs":[{"jobId":"job","sysParam":"{\"plogUploadSuccess\":\"1\"}"}]}}`)
					}
				case "queryJobLogIsExist":
					if r.URL.Query().Get("jobId") != "job" {
						t.Error("wrong job")
					}
					fmt.Fprint(w, `{"result":{"code":0,"isExistLog":false}}`)
				case "downloadPlog":
					linkCount++
					fmt.Fprintf(w, `{"result":{"code":0,"plogUrl":%q}}`, storage.URL)
				default:
					t.Errorf("unexpected request %s", r.URL.Path)
					http.NotFound(w, r)
				}
			}))
			defer server.Close()
			paths := fixtureConfig(t, t.TempDir(), server.URL, server.URL, false, tc.manager, "")
			saveState(t, paths, server.URL)
			args := append([]string{"train", "logs", "download", "task"}, tc.flags...)
			if tc.name == "history table" || tc.name == "history roles" {
				args = append(args, "-o", "table")
			} else {
				args = append(args, "--agent")
			}
			code, out, stderr := run(t, paths, append(args, "--directory", dir)...)
			if tc.name == "history table" || tc.name == "history roles" {
				if code != tc.code || !strings.Contains(stderr, "配额等待时间") || !strings.Contains(stderr, "作业ID") || !strings.Contains(stderr, "┏") {
					t.Fatalf("history query output: %s", stderr)
				}
				if tc.name == "history roles" && (!strings.Contains(stderr, "编号") || !strings.Contains(stderr, "worker-id") || strings.Contains(stderr, "roleJobId=")) {
					t.Fatalf("role candidates: %s", stderr)
				}
				return
			}
			if code != tc.code || archiveCount != tc.archives || linkCount != tc.links {
				t.Fatalf("exit %d, archives %d, links %d: %s %s", code, archiveCount, linkCount, out, stderr)
			}
			if !json.Valid([]byte(out)) {
				t.Fatalf("invalid agent JSON: %s", out)
			}
			if tc.code == 2 {
				if !strings.Contains(stderr, "归档失败") {
					t.Fatal(stderr)
				}
				return
			}
			var result struct {
				Status, JobID, Source string
				Items                 []trainLogItem
			}
			if json.Unmarshal([]byte(out), &result) != nil || result.Status != tc.status || result.JobID != "job" {
				t.Fatal(out, stderr)
			}
			if tc.name != "history retry" && result.Source != tc.source {
				t.Fatal(result.Source)
			}
			if tc.name == "no automatic retry" && (strings.Count(stderr, "--retry") != 1 || strings.Index(stderr, "下载结果") > strings.Index(stderr, "--retry") || !strings.Contains(stderr, dir) || !strings.Contains(stderr, "已下载 1/3")) {
				t.Fatal(stderr)
			}
			files, err := os.ReadDir(dir)
			if err != nil || len(files) != tc.files {
				t.Fatal(files, err)
			}
			for _, item := range result.Items {
				if item.Status == "succeeded" {
					content, err := os.ReadFile(item.File)
					if err != nil || string(content) != "log file" {
						t.Fatal(item.File, err)
					}
				}
			}
		})
	}
}

func TestChooseLatestArchiveAndJob(t *testing.T) {
	var rows []platform.Record
	err := json.Unmarshal([]byte(`[{"jobId":"a","archiveId":"1","createTime":"2026-09-08T14:00:00+08:00"},{"jobId":"b","archiveId":"2","createTime":"2026-09-08T07:00:00Z"}]`), &rows)
	if err != nil {
		t.Fatal(err)
	}
	for range 2 {
		latest, err := latestArchive(rows)
		if err != nil || latest.Text("archiveId") != "2" {
			t.Fatal(latest, err)
		}
		latest, err = chooseTrainJob(rows, "", false)
		if err != nil || latest.Text("jobId") != "b" {
			t.Fatal(latest, err)
		}
		rows[0], rows[1] = rows[1], rows[0]
	}
	rows[0]["createTime"] = rows[1]["createTime"]
	if _, err := latestArchive(rows); err == nil {
		t.Fatal("accepted tied archive timestamps")
	}
	latest, err := chooseTrainJob(rows, "", false)
	if err != nil || latest.Text("jobId") != "b" {
		t.Fatal(latest, err)
	}
	delete(rows[0], "createTime")
	if _, err := latestArchive(rows); err == nil {
		t.Fatal("accepted missing archive timestamp")
	}
}

func TestUnifiedHistoryWait(t *testing.T) {
	for _, scenario := range []string{"ready", "deadline", "interrupt"} {
		t.Run(scenario, func(t *testing.T) {
			synctest.Test(t, func(t *testing.T) {
				cmd := &cobra.Command{}
				ctx, cancel := context.WithCancel(context.Background())
				defer cancel()
				cmd.SetContext(ctx)
				var progress bytes.Buffer
				r := trainLogRun{cmd: cmd, steps: logDownloadSteps{out: &progress}, options: trainLogOptions{wait: true, interval: 30, timeout: 120}, items: []*trainLogItem{{RoleID: "ready"}, {RoleID: "pending"}}}
				checks := 0
				err := r.pollHistory(func(query context.Context, i *trainLogItem) (string, error) {
					if i.RoleID == "ready" {
						return "ready", nil
					}
					checks++
					if checks == 1 {
						return "", platform.ErrLogNotReady
					}
					switch scenario {
					case "ready":
						time.Sleep(89 * time.Second)
						return "ready", nil
					case "interrupt":
						cancel()
						return "", context.Canceled
					default:
						<-query.Done()
						return "", query.Err()
					}
				}, func(i *trainLogItem, _ string) {
					if i.Status == "succeeded" {
						t.Error("repeated download")
					}
					if i.RoleID == "pending" {
						time.Sleep(2 * time.Second)
					}
					i.Status = "succeeded"
				})
				if progress.String() != "已下载 1/2 · 等待 pending · 30 秒后重查 · 剩余 120 秒\n" {
					t.Fatal(progress.String())
				}
				if checks != 2 {
					t.Fatal(checks)
				}
				switch scenario {
				case "ready":
					if err != nil || r.items[1].Status != "succeeded" {
						t.Fatal(err, r.items)
					}
				case "interrupt":
					if err != context.Canceled {
						t.Fatal(err)
					}
				case "deadline":
					if err != nil || r.items[1].Status != "wait_timeout" || r.waited != 120*time.Second {
						t.Fatal(err, r.waited, r.items)
					}
				}
			})
		})
	}
}

func TestUnifiedTreeAndRetryUsage(t *testing.T) {
	paths := fixtureConfig(t, t.TempDir(), "https://platform.example", "https://access.example", false, "wiserec", "")
	code, out, stderr := run(t, paths, "tree", "--all")
	if code != 0 || !strings.Contains(out, "download  按作业状态下载训练日志") {
		t.Fatal(code, out, stderr)
	}
	for _, line := range strings.Split(out, "\n") {
		if !strings.Contains(line, "── ") {
			continue
		}
		description := strings.Split(strings.TrimSpace(line), "  [")[0]
		runes := []rune(description)
		if unicode.IsPunct(runes[len(runes)-1]) {
			t.Errorf("tree description ends with punctuation: %s", line)
		}
	}
	for _, args := range [][]string{{"task", "--retry"}, {"task", "job", "--retry", "--role-job-id", "role"}, {"task", "job", "--retry", "--type", "plog"}, {"task", "--wait", "--no-wait"}} {
		var out, errout bytes.Buffer
		code := Run(context.Background(), Options{Args: append([]string{"train", "logs", "download"}, args...), Stdout: &out, Stderr: &errout})
		if code != 2 {
			t.Fatal(code, errout.String())
		}
	}
}
