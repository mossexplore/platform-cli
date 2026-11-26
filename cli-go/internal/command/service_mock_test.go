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

func TestServiceMockAcceptsDocumentSamples(t *testing.T) {
	const text = " {\n \"message\": \"中文\"\n} "
	const emptyInput = "[错误] 服务文档输入报文为空，请在该服务中补充相关信息后再次调用！"
	quoted, err := json.Marshal(text)
	if err != nil {
		t.Fatal(err)
	}
	for _, tc := range []struct {
		name, raw, sample, failure string
		host                       bool
	}{
		{name: "JSON string", raw: string(quoted), sample: text},
		{name: "JSON object", raw: `{"large":123456789012345678901234567890}`, sample: `{"large":123456789012345678901234567890}`},
		{name: "host using JSON array", raw: `[{"sample":true}]`, sample: `[{"sample":true}]`, host: true},
		{name: "host using BOM", raw: `"\ufeff{\"sample\":true}"`, sample: `{"sample":true}`, host: true},
		{name: "missing", failure: "缺少有效的 requestContent"},
		{name: "null", raw: "null", failure: "缺少有效的 requestContent"},
		{name: "empty", raw: `""`, failure: emptyInput},
		{name: "host using blank sample", raw: `"\ufeff \r\n"`, failure: emptyInput, host: true},
		{name: "invalid JSON", raw: `"{oops}"`, failure: "requestContent 不是有效 JSON", host: true},
	} {
		t.Run(tc.name, func(t *testing.T) {
			args := []string{"service", "mock", "service-id", "-o", "json"}
			command := "ml service mock"
			if tc.host {
				args = []string{"service", "host", "mock", "service-id", "--pod-ip", "10.0.0.1", "-o", "json"}
				command = "ml service host mock"
			}
			var calls atomic.Int32
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				assertBusinessHeader(t, r)
				switch path.Base(r.URL.Path) {
				case "check":
					assertAccess(t, w, r, command)
				case "queryServiceHostList":
					fmt.Fprint(w, `{"result":{"code":0,"count":1,"data":[{"nodeId":"node","nodeHost":"10.0.0.1:1234"}]}}`)
				case "queryServiceBaseInfoDetail":
					fmt.Fprint(w, `{"result":{"code":0,"serviceInfo":{"serviceName":"mock-target","serviceVersion":"test"},"modelInfo":{"businessId":"service-tenant"}}}`)
				case "queryServiceDoc":
					fields := `"serviceId":"service-id","businessId":"service-tenant"`
					if tc.raw != "" {
						fields += ",\"requestContent\":" + tc.raw
					}
					fmt.Fprintf(w, `{"result":{"code":0,"serviceDocument":{%s}}}`, fields)
				case "serviceMock":
					calls.Add(1)
					body := readRequest(t, r)
					data, ok := body["data"].(map[string]any)
					if !ok || data["requestSample"] != tc.sample || data["businessId"] != "service-tenant" {
						t.Errorf("unexpected mock body: %v", body)
					}
					if tc.host {
						node, _ := data["node"].(map[string]any)
						if node["hostId"] != "node" || node["hostAddress"] != "10.0.0.1:1234" {
							t.Errorf("unexpected host: %v", node)
						}
					}
					fmt.Fprint(w, `{"result":{"code":0,"nodeList":[{"retCode":0,"mockResponse":"{}"}]}}`)
				default:
					t.Errorf("unexpected request %s", r.URL.Path)
					w.WriteHeader(http.StatusNotFound)
				}
			}))
			defer server.Close()
			paths := fixtureConfig(t, t.TempDir(), server.URL, server.URL, false, "mlops", "")
			saveState(t, paths, server.URL)
			code, out, stderr := run(t, paths, args...)
			if tc.failure != "" {
				if code != 1 || out != "" || calls.Load() != 0 || !strings.Contains(stderr, tc.failure) {
					t.Fatalf("invalid sample not rejected (%d): %s\n%s", code, out, stderr)
				}
				return
			}
			if code != 0 || stderr != "" || !json.Valid([]byte(out)) || calls.Load() != 1 {
				t.Fatalf("sample not sent exactly once (%d): %s\n%s", code, out, stderr)
			}
			result := compactResult(t, paths, append(args[:len(args)-2], "--agent")...)
			if len(result["nodeList"].([]any)) != 1 || calls.Load() != 2 {
				t.Fatal(result, calls.Load())
			}
		})
	}
}
