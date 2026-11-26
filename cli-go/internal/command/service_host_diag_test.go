package command

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"path"
	"strings"
	"sync/atomic"
	"testing"
)

func TestServiceHostPodEventTableAndJSON(t *testing.T) {
	for _, manager := range []string{"wiserec", "mlops"} {
		t.Run(manager, func(t *testing.T) {
			var hostCalls, eventCalls atomic.Int32
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				assertBusinessHeader(t, r)
				switch path.Base(r.URL.Path) {
				case "check":
					command, _ := readRequest(t, r)["command"].(string)
					if command != "ml service host list" && command != "ml service host pod-event" {
						t.Errorf("unexpected admission command: %s", command)
					}
					fmt.Fprint(w, `{"allowed":true,"username":"preview-user","environment":"preview"}`)
				case "queryServiceHostList":
					hostCalls.Add(1)
					fmt.Fprint(w, `{"result":{"code":0,"count":1,"data":[{"nodeName":"test-fb49d6d85-q2mxh","clusterName":"test-mirror-npu-arm"}]}}`)
				case "queryPodEvent":
					eventCalls.Add(1)
					body := readRequest(t, r)
					if body["businessId"] != "business-real" || body["podName"] != "test-fb49d6d85-q2mxh" || body["clusterName"] != "test-mirror-npu-arm" {
						t.Errorf("unexpected pod event request body: %v", body)
					}
					fmt.Fprint(w, `{
						"version":"1.0.0",
						"meta":{"uuid":"ad6c81a3-fa0e-4d86-adc9-8437023cf298"},
						"result":{
							"code":0,
							"des":"success",
							"eventContents":[
								{
									"type":"Warning",
									"reason":"Unhealthy",
									"message":"Liveness probe failed: dial tcp 10.1.1.1:0->10.20.1.1:18090: connect: connection refused",
									"lastTimestamp":"2026-11-19T11:30:23Z",
									"count":31411
								},
								{
									"type":"Warning",
									"reason":"Unhealthy",
									"message":"Readiness probe failed: dial tcp 10.1.1.1:0->10.20.1.1:18090: connect: connection refused",
									"lastTimestamp":"2026-11-19T11:25:23Z",
									"count":31381
								}
							]
						}
					}`)
				default:
					t.Errorf("unexpected path: %s", r.URL.Path)
					w.WriteHeader(http.StatusNotFound)
				}
			}))
			defer server.Close()

			paths := fixtureConfig(t, t.TempDir(), server.URL, server.URL, false, manager, "")
			saveState(t, paths, server.URL)

			// Direct mode: --pod + --cluster-name without SERVICE_ID (zero host list calls).
			code, out, stderr := run(t, paths, "service", "host", "pod-event", "--pod", "test-fb49d6d85-q2mxh", "--cluster-name", "test-mirror-npu-arm")
			if code != 0 || stderr != "" || hostCalls.Load() != 0 || eventCalls.Load() != 1 {
				t.Fatalf("direct pod-event failed: code=%d hostCalls=%d eventCalls=%d stderr=%q out=%q", code, hostCalls.Load(), eventCalls.Load(), stderr, out)
			}
			for _, want := range []string{"类型", "事件原因", "消息", "最后更新时间", "次数", "Warning", "Unhealthy", "2026-11-19 19:30:23", "31411", "2026-11-19 19:25:23", "31381"} {
				if !strings.Contains(out, want) {
					t.Fatalf("table output missing %q:\n%s", want, out)
				}
			}

			// SERVICE_ID mode: single host auto-selected, JSON output.
			code, out, stderr = run(t, paths, "service", "host", "pod-event", "svc-1", "-o", "json")
			if code != 0 || stderr != "" || hostCalls.Load() != 1 || eventCalls.Load() != 2 || !json.Valid([]byte(out)) {
				t.Fatalf("service-id pod-event json failed: code=%d hostCalls=%d eventCalls=%d stderr=%q out=%q", code, hostCalls.Load(), eventCalls.Load(), stderr, out)
			}

			list := compactResult(t, paths, "service", "host", "list", "svc-1", "--agent")
			row := list["items"].([]any)[0].(map[string]any)
			events := compactResult(t, paths, "service", "host", "pod-event", "--agent",
				"--pod", row["nodeName"].(string), "--cluster-name", row["clusterName"].(string))
			event := events["items"].([]any)[0].(map[string]any)
			if hostCalls.Load() != 2 || eventCalls.Load() != 3 || event["count"] != float64(31411) ||
				event["lastTimestamp"] != "2026-11-19 19:30:23" || events["fields"].(map[string]any)["count"] == nil {
				t.Fatal(list, events, hostCalls.Load(), eventCalls.Load())
			}
		})
	}
}

func TestServiceHostPodEventEmptyAndServicePodLookup(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		assertBusinessHeader(t, r)
		switch path.Base(r.URL.Path) {
		case "check":
			assertAccess(t, w, r, "ml service host pod-event")
		case "queryServiceHostList":
			fmt.Fprint(w, `{"result":{"code":0,"count":2,"data":[{"nodeName":"pod-a","clusterName":"cluster-a"},{"nodeName":"pod-b","clusterName":"cluster-b"}]}}`)
		case "queryPodEvent":
			body := readRequest(t, r)
			if body["podName"] != "pod-b" || body["clusterName"] != "cluster-b" {
				t.Errorf("unexpected body: %v", body)
			}
			fmt.Fprint(w, `{"result":{"code":0,"des":"success","eventContents":[]}}`)
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()

	paths := fixtureConfig(t, t.TempDir(), server.URL, server.URL, false, "wiserec", "")
	saveState(t, paths, server.URL)

	code, out, stderr := run(t, paths, "service", "host", "pod-event", "svc-1", "--pod", "pod-b")
	if code != 0 || stderr != "" || !strings.Contains(out, "暂无 Pod 事件") {
		t.Fatalf("empty pod-event failed: code=%d stderr=%q out=%q", code, stderr, out)
	}

	// Usage errors.
	code, _, stderr = run(t, paths, "service", "host", "pod-event")
	if code != 2 || !strings.Contains(stderr, "请提供 SERVICE_ID") {
		t.Fatalf("expected usage error when no args/flags: code=%d stderr=%q", code, stderr)
	}
	code, _, stderr = run(t, paths, "service", "host", "pod-event", "--cluster-name", "cluster-a")
	if code != 2 || !strings.Contains(stderr, "必须同时指定 --pod") {
		t.Fatalf("expected usage error for cluster without pod: code=%d stderr=%q", code, stderr)
	}
}

func TestServiceHostLogStdoutDynamicContainers(t *testing.T) {
	for _, manager := range []string{"wiserec", "mlops"} {
		t.Run(manager, func(t *testing.T) {
			var containers []string
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				assertBusinessHeader(t, r)
				switch path.Base(r.URL.Path) {
				case "check":
					assertAccess(t, w, r, "ml service host log-stdout")
				case "queryServiceHostList":
					fmt.Fprint(w, `{"result":{"code":0,"count":1,"data":[{"nodeName":"test001","clusterName":"cluster-a"}]}}`)
				case "queryPodLog":
					body := readRequest(t, r)
					if body["businessId"] != "business-real" || body["podName"] != "test001" {
						t.Errorf("unexpected queryPodLog body: %v", body)
					}
					name, _ := body["containerName"].(string)
					containers = append(containers, name)
					content := "2026-11-19T11:46:10.523164588Z the request body contain reqData\\n2026-11-19T11:46:10.523533608Z [2026-11-19 19:46:10 +0800] [16]: [INFO] start check doing task"
					if name == "init1container" {
						content = "init line 1\\ninit line 2"
					}
					fmt.Fprintf(w, `{
						"version":"1.0.0",
						"meta":{"uuid":"3c66ba0f-f4b1-410f-a633-a46a9545c2a9"},
						"result":{
							"code":0,
							"des":"success",
							"data":{"content":"%s"},
							"containerStates":[
								{"name":"appcontainer","state":"running","restartCount":0,"exitCode":0},
								{"name":"filebeat","state":"running","restartCount":0,"exitCode":0},
								{"name":"registercontainer","state":"running","restartCount":0,"exitCode":0},
								{"name":"init1container","state":"running","restartCount":4051,"exitCode":1,"reason":"Error"}
							]
						}
					}`, content)
				default:
					t.Errorf("unexpected path: %s", r.URL.Path)
					w.WriteHeader(http.StatusNotFound)
				}
			}))
			defer server.Close()

			paths := fixtureConfig(t, t.TempDir(), server.URL, server.URL, false, manager, "")
			saveState(t, paths, server.URL)

			// 1. Default appcontainer via --pod (single API call).
			containers = nil
			code, out, stderr := run(t, paths, "service", "host", "log-stdout", "--pod", "test001")
			if code != 0 || stderr != "" || len(containers) != 1 || containers[0] != "appcontainer" {
				t.Fatalf("default log-stdout failed: code=%d containers=%v stderr=%q out=%q", code, containers, stderr, out)
			}
			want := strings.Join([]string{
				"容器名称：appcontainer，重启次数：0，状态：running",
				"容器名称：filebeat，重启次数：0，状态：running",
				"容器名称：registercontainer，重启次数：0，状态：running",
				"容器名称：init1container，重启次数：4051，状态：running",
				"详细日志：",
				"2026-11-19T11:46:10.523164588Z the request body contain reqData",
				"2026-11-19T11:46:10.523533608Z [2026-11-19 19:46:10 +0800] [16]: [INFO] start check doing task",
				"",
			}, "\n")
			if out != want {
				t.Fatalf("unexpected log-stdout output:\ngot:\n%s\nwant:\n%s", out, want)
			}

			// 2. Custom existing container via SERVICE_ID + -c (probe appcontainer, then fetch target).
			containers = nil
			code, out, stderr = run(t, paths, "service", "host", "log-stdout", "svc-1", "-c", "init1container")
			if code != 0 || stderr != "" || len(containers) != 2 || containers[0] != "appcontainer" || containers[1] != "init1container" {
				t.Fatalf("custom container failed: code=%d containers=%v stderr=%q out=%q", code, containers, stderr, out)
			}
			if !strings.Contains(out, "init line 1\ninit line 2\n") {
				t.Fatalf("expected target container log lines:\n%s", out)
			}

			// 3. Non-existent container: probe only once, print exact prompt.
			containers = nil
			code, out, stderr = run(t, paths, "service", "host", "log-stdout", "--pod", "test001", "-c", "sidecar")
			if code != 1 || out != "" || len(containers) != 1 || !strings.Contains(stderr, "该容器没有sidecar类型日志，请确认容器类型是否正确！") {
				t.Fatalf("missing container not rejected properly: code=%d containers=%v stderr=%q out=%q", code, containers, stderr, out)
			}

			// 4. JSON output.
			containers = nil
			code, out, stderr = run(t, paths, "service", "host", "log-stdout", "--pod", "test001", "-o", "json")
			if code != 0 || stderr != "" || !json.Valid([]byte(out)) || !strings.Contains(out, `"containerStates"`) {
				t.Fatalf("json output failed: code=%d stderr=%q out=%q", code, stderr, out)
			}
		})
	}
}

func TestServiceLogsRemovedAndTreeUpdated(t *testing.T) {
	for _, manager := range []string{"wiserec", "mlops"} {
		paths := fixtureConfig(t, t.TempDir(), "https://preview.example.test", "", false, manager, "")
		code, out, stderr := run(t, paths, "tree")
		if code != 0 || stderr != "" {
			t.Fatalf("%s tree failed: code=%d stderr=%q", manager, code, stderr)
		}
		for _, want := range []string{
			"log-search  检索指定主机的业务日志文件",
			"log-stdout  查询指定主机的标准输出日志",
			"pod-event  查询指定主机的 Pod 事件",
		} {
			if !strings.Contains(out, want) {
				t.Fatalf("%s tree missing %q:\n%s", manager, want, out)
			}
		}
		if strings.Contains(out, "logs  选择服务主机和文件并查看日志") {
			t.Fatalf("%s tree still contains removed ml service logs:\n%s", manager, out)
		}

		// The help panel lists the registered Go service diagnostics.
		code, out, stderr = run(t, paths, "service", "host", "--help")
		if code != 0 || stderr != "" || !strings.Contains(out, "pod-event") || !strings.Contains(out, "log-stdout") || !strings.Contains(out, "log-search") {
			t.Fatalf("%s service host --help failed: code=%d stderr=%q out=%q", manager, code, stderr, out)
		}
	}

	paths := fixtureConfig(t, t.TempDir(), "https://preview.example.test", "", false, "wiserec", "")
	code, _, stderr := run(t, paths, "service", "logs", "svc-1")
	if code == 0 || !strings.Contains(stderr, `unknown command "logs"`) {
		t.Fatalf("expected ml service logs to be removed: code=%d stderr=%q", code, stderr)
	}
}

func TestServiceHostListHidesDeployIDInTableAndKeepsInJSON(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		assertBusinessHeader(t, r)
		switch path.Base(r.URL.Path) {
		case "check":
			assertAccess(t, w, r, "ml service host list")
		case "queryServiceHostList":
			fmt.Fprint(w, `{"result":{"code":0,"count":1,"data":[{"deployId":"dep-123456","clusterName":"cluster-a","nodeName":"pod-a","nodeHost":"10.0.0.1:8080","hostIp":"10.0.0.2","spec":"2C4G","health_status":"0"}]}}`)
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()

	paths := fixtureConfig(t, t.TempDir(), server.URL, server.URL, false, "wiserec", "")
	saveState(t, paths, server.URL)

	code, out, stderr := run(t, paths, "service", "host", "list", "svc-1")
	if code != 0 || stderr != "" {
		t.Fatalf("host list table failed: code=%d stderr=%q out=%q", code, stderr, out)
	}
	if strings.Contains(out, "部署 ID") || strings.Contains(out, "dep-123456") {
		t.Fatalf("host list table should not display deployId column:\n%s", out)
	}
	if !strings.Contains(out, "集群") || !strings.Contains(out, "pod名称") {
		t.Fatalf("host list table missing expected columns:\n%s", out)
	}

	code, out, stderr = run(t, paths, "service", "host", "list", "svc-1", "-o", "json")
	if code != 0 || stderr != "" || !json.Valid([]byte(out)) || !strings.Contains(out, `"deployId": "dep-123456"`) {
		t.Fatalf("host list json should retain deployId: code=%d stderr=%q out=%q", code, stderr, out)
	}
}
