package command

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path"
	"path/filepath"
	"sync/atomic"
	"testing"
)

func TestAgentDatasetUploadReportsTarget(t *testing.T) {
	const fileContent = "a,b\n1,2\n"
	var uploads atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		assertBusinessHeader(t, r)
		switch path.Base(r.URL.Path) {
		case "check":
			assertAccess(t, w, r, "ml dataset files upload")
		case "queryDetail":
			fmt.Fprint(w, `{"result":{"code":0,"data":{"dataSetName":"upload-dataset"}}}`)
		case "upload":
			uploads.Add(1)
			f, header, err := r.FormFile("file")
			if err != nil {
				t.Error(err)
				http.Error(w, "missing file", http.StatusBadRequest)
				return
			}
			defer f.Close()
			content, err := io.ReadAll(f)
			var metadata struct {
				Data map[string]string
			}
			if err != nil || string(content) != fileContent || header.Filename != "sample.csv" ||
				r.URL.Query().Get("target") != "upload-dataset" ||
				json.Unmarshal([]byte(r.FormValue("params")), &metadata) != nil ||
				metadata.Data["dir"] != "/data" || metadata.Data["dataSetId"] != "ds-id" {
				t.Errorf("unexpected upload metadata or bytes: %v %q", metadata, content)
			}
			fmt.Fprint(w, `{"result":{"code":0,"des":"success"}}`)
		default:
			t.Errorf("unexpected route %s", r.URL.Path)
			http.NotFound(w, r)
		}
	}))
	defer server.Close()
	dir := t.TempDir()
	paths := fixtureConfig(t, dir, server.URL, server.URL, false, "wiserec", "")
	saveState(t, paths, server.URL)
	file := filepath.Join(dir, "sample.csv")
	if err := os.WriteFile(file, []byte(fileContent), 0600); err != nil {
		t.Fatal(err)
	}
	result := compactResult(t, paths, "dataset", "files", "upload", "ds-id", file, "--dir", "/data/", "--agent")
	if uploads.Load() != 1 || result["status"] != "accepted" || result["dataSetId"] != "ds-id" ||
		result["dataSetName"] != "upload-dataset" || result["directory"] != "/data" || result["fileName"] != "sample.csv" {
		t.Fatal(result, uploads.Load())
	}
}

func TestAgentSwanExperimentPage(t *testing.T) {
	for _, tc := range []struct {
		name, response string
		size, total    any
	}{
		{"known", `{"pageNum":1,"pageSize":20,"total":0,"list":[]}`, float64(20), float64(0)},
		{"unreported", `{"list":[{"experimentId":"e1","name":"test","createTime":"2026-09-08T06:54:36Z"}]}`, nil, nil},
	} {
		t.Run(tc.name, func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				assertBusinessHeader(t, r)
				switch path.Base(r.URL.Path) {
				case "check":
					assertAccess(t, w, r, "ml mtp swanboard project experiment list")
				case "page":
					fmt.Fprintf(w, `{"result":{"code":0,"data":%s}}`, tc.response)
				default:
					http.NotFound(w, r)
				}
			}))
			defer server.Close()
			paths := fixtureConfig(t, t.TempDir(), server.URL, server.URL, false, "wiserec", "")
			saveState(t, paths, server.URL)
			result := compactResult(t, paths, "mtp", "swanboard", "project", "experiment", "list", "project", "namespace", "--agent")
			size, hasSize := result["pageSize"]
			_, hasTotal := result["total"]
			if result["pagination"] != "fixedFirstPage" || result["pageIndex"] != float64(1) ||
				!hasSize || size != tc.size || hasTotal != (tc.total != nil) || result["total"] != tc.total ||
				result["fields"].(map[string]any)["experimentId"] != "实验 ID" {
				t.Fatal(result)
			}
		})
	}
}

func TestAgentTrainHistorySelectsReadyPlog(t *testing.T) {
	const readyID = "00000000-0000-4000-8000-000000000001"
	const log = "worker log\n"
	var downloads atomic.Int32
	storage := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		downloads.Add(1)
		fmt.Fprint(w, log)
	}))
	defer storage.Close()
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		assertBusinessHeader(t, r)
		switch path.Base(r.URL.Path) {
		case "check":
			cmd := readRequest(t, r)["command"]
			if cmd != "ml train history list" && cmd != "ml train history logs download" {
				t.Errorf("unexpected admission command: %v", cmd)
			}
			fmt.Fprint(w, `{"allowed":true,"username":"preview-user","environment":"preview"}`)
		case "queryScheduleTaskList":
			fmt.Fprintf(w, `{"result":{"code":0,"count":2,"jobs":[
				{"taskId":"task","jobId":"job","jobType":"dps-train","roleJobInfo":[
					{"taskId":"task","jobId":"job","roleJobId":%q,"roleType":"worker","status":"COMPLETE","sysParam":"{\"plogUploadSuccess\":\"1\"}"},
					{"roleJobId":"pending","roleType":"chief","status":"RUNNING"}]},
				{"taskId":"task","jobId":"regular","sysParam":"{\"plogUploadSuccess\":\"1\"}"}
			]}}`, readyID)
		case "downloadPlog":
			if r.URL.Query().Get("roleJobId") != readyID || r.URL.Query().Get("jobId") != "job" {
				t.Errorf("unexpected plog request %s", r.URL.RawQuery)
			}
			fmt.Fprintf(w, `{"result":{"code":0,"plogUrl":%q}}`, storage.URL)
		default:
			t.Errorf("unexpected route %s", r.URL.Path)
			http.NotFound(w, r)
		}
	}))
	defer server.Close()
	paths := fixtureConfig(t, t.TempDir(), server.URL, server.URL, false, "mlops", "")
	saveState(t, paths, server.URL)
	list := compactResult(t, paths, "train", "history", "list", "task", "--latest-flag", "all", "--agent")
	jobs := list["items"].([]any)
	job := jobs[0].(map[string]any)
	roles := job["roleJobInfo"].([]any)
	ready := roles[0].(map[string]any)
	if ready["plogReady"] != true || ready["status"] != "COMPLETE" ||
		roles[1].(map[string]any)["plogReady"] != false || jobs[1].(map[string]any)["plogReady"] != true ||
		list["fields"].(map[string]any)["roleJobInfo.plogReady"] == nil {
		t.Fatal(list)
	}
	destination := t.TempDir()
	result := compactResult(t, paths, "train", "history", "logs", "download", "task", job["jobId"].(string),
		"--role-job-id", ready["roleJobId"].(string), "--type", "plog", "--directory", destination, "--agent")
	files, err := os.ReadDir(destination)
	if err != nil || len(files) != 1 || downloads.Load() != 1 || result["status"] != "downloaded" {
		t.Fatal(result, files, err, downloads.Load())
	}
	content, err := os.ReadFile(filepath.Join(destination, files[0].Name()))
	if err != nil || string(content) != log {
		t.Fatal(string(content), err)
	}
}

func TestAgentJupyterFileListAndRead(t *testing.T) {
	t.Setenv("ML_JUPYTER_TOKEN", "fixture-jupyter")
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		assertBusinessHeader(t, r)
		switch r.URL.Path {
		case "/cli-permission/api/v1/access/check":
			command := readRequest(t, r)["command"]
			if command != "ml jupyter files list" && command != "ml jupyter files read" {
				t.Errorf("unexpected admission command: %v", command)
			}
			fmt.Fprint(w, `{"allowed":true,"username":"preview-user","environment":"preview"}`)
		case "/jupyter/api/contents/":
			if r.URL.Query().Get("content") != "1" {
				t.Errorf("directory contents not requested")
			}
			fmt.Fprint(w, `{"type":"directory","path":"","content":[{"name":"notes.txt","path":"notes.txt","type":"file","size":0,
				"writable":false,"last_modified":"2026-09-08T06:54:36Z","content":null}]}`)
		case "/jupyter/api/contents/notes.txt":
			if r.URL.Query().Get("content") != "1" || r.URL.Query().Get("format") != "text" {
				t.Errorf("unexpected read options: %s", r.URL.RawQuery)
			}
			fmt.Fprint(w, `{"type":"file","content":"第一行\r\n第二行\r\n第三行\n"}`)
		default:
			t.Errorf("unexpected route: %s", r.URL.Path)
			http.NotFound(w, r)
		}
	}))
	defer server.Close()
	paths := fixtureConfig(t, t.TempDir(), server.URL, server.URL, false, "mlops", server.URL+"/jupyter/")
	saveState(t, paths, server.URL)
	list := compactResult(t, paths, "jupyter", "files", "list", "--agent")
	file := list["items"].([]any)[0].(map[string]any)
	_, hasContent := file["content"]
	if file["size"] != float64(0) || file["writable"] != false || hasContent ||
		file["last_modified"] != "2026-09-08 14:54:36" || list["fields"].(map[string]any)["size"] == nil {
		t.Fatal(list)
	}
	result := compactResult(t, paths, "jupyter", "files", "read", file["path"].(string), "--start-line", "2", "--end-line", "2", "--agent")
	if result["content"] != "第二行\r\n" || result["start_line"] != float64(2) || result["end_line"] != float64(2) {
		t.Fatal(result)
	}
}
