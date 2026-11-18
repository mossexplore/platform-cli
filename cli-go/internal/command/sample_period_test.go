package command

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestSamplePeriodListUsesFourColumnGrid(t *testing.T) {
	t.Setenv("COLUMNS", "112")
	for _, count := range []int{0, 1, 7, 21} {
		t.Run(fmt.Sprintf("%d periods", count), func(t *testing.T) {
			items := make([]map[string]any, count)
			for index := range items {
				items[index] = map[string]any{"period": fmt.Sprintf("period-%02d", index+1), "state": "COMPLETED", "extra": true}
			}
			if count > 4 {
				items[4]["state"] = "NEW_STATE"
			}
			if count > 6 {
				items[6] = map[string]any{"period": nil, "state": ""}
			}
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				assertBusinessHeader(t, r)
				switch r.URL.Path {
				case "/cli-permission/api/v1/access/check":
					assertAccess(t, w, r, "ml sample-task period list")
				case "/ai/backend/dpp/proxy/schedule-service/task/instances/query":
					body := readRequest(t, r)
					data, _ := body["data"].(map[string]any)
					if r.Method != http.MethodPost || data["taskId"] != "sample-task-id" || data["businessId"] != "business-real" ||
						data["pageIndex"] != float64(2) || data["pageSize"] != float64(30) {
						t.Errorf("unexpected query: %s %v", r.Method, body)
					}
					_ = json.NewEncoder(w).Encode(map[string]any{
						"result": map[string]any{"code": 0, "count": count, "instances": items},
					})
				default:
					t.Errorf("unexpected route: %s", r.URL.Path)
					w.WriteHeader(http.StatusNotFound)
				}
			}))
			defer server.Close()
			paths := fixtureConfig(t, t.TempDir(), server.URL, server.URL, false, "wiserec", "")
			saveState(t, paths, server.URL)
			args := []string{"sample-task", "period", "list", "sample-task-id", "--page", "2", "--page-size", "30"}
			code, out, stderr := run(t, paths, args...)
			if code != 0 || stderr != "" {
				t.Fatalf("period query: %d %s %s", code, out, stderr)
			}
			header := "任务 ID：sample-task-id\n"
			footer := fmt.Sprintf("第 2 页 · 每页 30 条 · 共 %d 条\n", count)
			if !strings.HasPrefix(out, header) || !strings.HasSuffix(out, footer) {
				t.Fatalf("unexpected header or footer: %s", out)
			}
			grid := strings.TrimSuffix(strings.TrimPrefix(out, header), footer)
			if count == 0 {
				if grid != "暂无执行周期\n" {
					t.Fatalf("empty result: %s", out)
				}
				return
			}
			var cells []string
			for _, line := range strings.Split(grid, "\n") {
				if strings.HasPrefix(line, "│") {
					columns := strings.Split(line, "│")
					if len(columns) != 6 {
						t.Fatalf("expected four columns: %s", line)
					}
					cells = append(cells, columns[1:5]...)
				}
			}
			rows := (count + 3) / 4
			if len(cells) != rows*4 || !strings.HasPrefix(grid, "┌") || strings.Count(grid, "├") != rows-1 {
				t.Fatalf("unexpected grid shape: %s", grid)
			}
			for index, value := range cells {
				want := ""
				switch {
				case index == 4 && index < count:
					want = "5 period-05 NEW_STATE"
				case index == 6 && index < count:
					want = "7 - -"
				case index < count:
					want = fmt.Sprintf("%d period-%02d 运行成功", index+1, index+1)
				}
				if strings.TrimSpace(value) != want {
					t.Fatalf("grid cell %d: got %q, want %q\n%s", index+1, value, want, grid)
				}
			}
			if count == 7 {
				code, out, stderr = run(t, paths, append(args, "-o", "json")...)
				var result struct {
					TaskID                string
					Page, PageSize, Total int
					Items                 []map[string]any
				}
				if code != 0 || stderr != "" || json.Unmarshal([]byte(out), &result) != nil || result.TaskID != "sample-task-id" ||
					result.Page != 2 || result.PageSize != 30 || result.Total != count || len(result.Items) != count ||
					result.Items[0]["state"] != "COMPLETED" || result.Items[0]["extra"] != true || result.Items[6]["state"] != "" {
					t.Fatalf("unexpected JSON output: %d %s %s", code, out, stderr)
				}
			}
		})
	}
}
