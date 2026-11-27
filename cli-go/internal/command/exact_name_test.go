package command

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestExactNameFlagAcrossSupportedLists(t *testing.T) {
	cases := []struct {
		name      string
		args      []string
		route     string
		field     string
		nested    bool
		response  string
		wantValue string
	}{
		{
			name:      "train list",
			args:      []string{"train", "list", "--name", "recall_v3", "--exact", "--agent"},
			route:     "/ai/backend/modelDev/modelTrain/list",
			field:     "taskName",
			nested:    true,
			response:  `{"result":{"code":0,"data":{"count":0,"taskInfos":[]}}}`,
			wantValue: "recall_v3,recall_v3",
		},
		{
			name:      "model list",
			args:      []string{"model", "list", "--name", "rank_m1", "--exact", "--agent"},
			route:     "/ai/backend/mep/models/queryList",
			field:     "modelName",
			response:  `{"result":{"code":0,"count":0,"models":[]}}`,
			wantValue: "rank_m1,rank_m1",
		},
		{
			name:      "algorithm list via alias",
			args:      []string{"algorithm", "list", "--algorithm-name", "algo_x", "--exact", "--agent"},
			route:     "/ai/backend/modelDev/algorithmWarehouse/list",
			field:     "algorithmName",
			nested:    true,
			response:  `{"result":{"code":0,"data":{"total":0,"list":[]}}}`,
			wantValue: "algo_x,algo_x",
		},
		{
			name:      "dataset list via alias",
			args:      []string{"dataset", "list", "--dataset-name", "ds_a", "--exact", "--agent"},
			route:     "/ai/backend/mtp/dataSet/queryList",
			field:     "dataSetName",
			response:  `{"result":{"code":0,"totalSize":0,"data":[]}}`,
			wantValue: "ds_a,ds_a",
		},
		{
			name:      "service list via alias",
			args:      []string{"service", "list", "--service-name", "svc_1", "--exact", "--agent"},
			route:     "/ai/backend/mep/services/queryList",
			field:     "serviceName",
			response:  `{"result":{"code":0,"count":0,"services":[]}}`,
			wantValue: "svc_1,svc_1",
		},
		{
			name:      "feature-task list",
			args:      []string{"feature-task", "list", "--name", "ft_1", "--exact", "--agent"},
			route:     "/ai/backend/mtp/traintask/queryList",
			field:     "taskName",
			response:  `{"result":{"code":0,"count":0,"taskInfos":[]}}`,
			wantValue: "ft_1,ft_1",
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			var gotField string
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if strings.HasSuffix(r.URL.Path, "/access/check") {
					assertAccess(t, w, r, "ml "+tc.args[0]+" "+tc.args[1])
					return
				}
				if r.URL.Path != tc.route {
					t.Errorf("unexpected route %s, want %s", r.URL.Path, tc.route)
				}
				var body map[string]any
				if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
					t.Fatal(err)
				}
				target := body
				if tc.nested {
					target, _ = body["data"].(map[string]any)
				}
				gotField, _ = target[tc.field].(string)
				_, _ = w.Write([]byte(tc.response))
			}))
			defer server.Close()

			paths := fixtureConfig(t, t.TempDir(), server.URL, server.URL, false, "wiserec", "")
			saveState(t, paths, server.URL)
			code, _, stderr := run(t, paths, tc.args...)
			if code != 0 {
				t.Fatalf("code=%d stderr=%s", code, stderr)
			}
			if gotField != tc.wantValue {
				t.Fatalf("field %s = %q, want %q", tc.field, gotField, tc.wantValue)
			}
		})
	}
}

func TestExactNameFlagValidation(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if strings.HasSuffix(r.URL.Path, "/access/check") {
			var req map[string]any
			_ = json.NewDecoder(r.Body).Decode(&req)
			_ = json.NewEncoder(w).Encode(map[string]any{"allowed": true, "username": req["username"], "environment": req["environment"]})
			return
		}
		t.Fatalf("business API should not be called on invalid --exact usage: %s", r.URL.Path)
	}))
	defer server.Close()

	paths := fixtureConfig(t, t.TempDir(), server.URL, server.URL, false, "wiserec", "")
	saveState(t, paths, server.URL)
	for _, tc := range []struct {
		name string
		args []string
		want string
	}{
		{"missing name on model", []string{"model", "list", "--exact", "--agent"}, "必须提供名称"},
		{"missing name on train", []string{"train", "list", "--exact", "--agent"}, "必须提供名称"},
		{"comma in name on service", []string{"service", "list", "--name", "a,b", "--exact", "--agent"}, "英文逗号"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			code, _, stderr := run(t, paths, tc.args...)
			if code != 2 || !strings.Contains(stderr, tc.want) {
				t.Fatalf("code=%d stderr=%s, want exit 2 containing %q", code, stderr, tc.want)
			}
		})
	}
}
