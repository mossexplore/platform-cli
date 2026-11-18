package command

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"

	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
)

func TestModelDeployDryRunBuildsPayloadWithoutPublishing(t *testing.T) {
	paths := localstate.Paths{Dir: t.TempDir()}
	var publishes atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		assertBusinessHeader(t, r)
		switch r.URL.Path {
		case "/cli-permission/api/v1/access/check":
			assertAccess(t, w, r, "ml model deploy")
		case "/ai/backend/mep/models/queryDetail":
			fmt.Fprintln(w, `{"result":{"code":0,"modelId":"model-1","modelName":"模型","modelVersion":"1","source":"source","sourceId":"source-1","modelTag":"","pkgId":"pkg","modelType":"type","pkgSize":25,"pkgLocation":"path","businessId":"business-real","storeType":"OBS"}}`)
		case "/ai/backend/mep/scm/deploytemplate/queryDetail":
			fmt.Fprintln(w, `{"result":{"code":0,"template":{"deployTemplateId":"template-1","deployTemplateType":"docker","businessId":"business-real","inferenceType":"online","env":"dev","serviceTimeout":"500","executeLimit":"8","dockerResourceTemplate":["resource"]}}}`)
		case "/ai/backend/mep/resourcetemp/queryList":
			fmt.Fprintln(w, `{"result":{"code":0,"resourceTemplateInfoList":[{"dockerId":"docker-1","dockerResourceTemplateName":"resource"}]}}`)
		case "/ai/backend/mep/resourcetemp/queryDetail":
			fmt.Fprintln(w, `{"result":{"code":0,"dockerResourceTemplateName":"resource","frameworkPkgId":"framework-1","frameworkConfiguration":{"stream":{"opt":1}},"memory":"8G","quotaType":"quota","containerSpec":"yaml","clusterName":"cluster","appImageName":"image","imageTag":"tag","cpu":"4"}}`)
		case "/ai/backend/mep/scm/frameworkPkg/queryFrameworkPkgDetail":
			fmt.Fprintln(w, `{"result":{"code":0,"data":{"name":"framework","version":"1","pkgStorageId":"pkg","pkgStorageLocation":"location","storageType":"OBS"}}}`)
		case "/ai/user/queryTenantDetail":
			if r.Method != "GET" || r.URL.Query().Get("businessId") != "tenant" {
				t.Errorf("must query true tenant with current selected business header")
			}
			fmt.Fprintln(w, `{"result":{"code":0,"data":{"tenantServiceEntityList":[{"serviceGroup":"scope"}]}}}`)
		case "/ai/backend/mep/services/rtcContainer/publish":
			publishes.Add(1)
			fmt.Fprintln(w, `{"result":{"code":0}}`)
		default:
			t.Errorf("unexpected route %s", r.URL.Path)
		}
	}))
	defer server.Close()
	writeConfig(t, paths, server.URL, server.URL, false)
	saveState(t, paths, server.URL)
	code, out, stderr := run(t, paths, "model", "deploy", "model-1", "--template", "template-1", "--execute-limit", "2", "--dry-run", "--yes", "-o", "json")
	var payload struct {
		Version string
		Data    struct {
			Service map[string]any `json:"serviceInfo"`
			Health  map[string]any `json:"extendConfiguration"`
			Blocks  []struct {
				Image string `json:"imageName"`
			} `json:"serviceBlocks"`
		} `json:"data"`
	}
	if code != 0 || stderr != "" || publishes.Load() != 0 || json.Unmarshal([]byte(out), &payload) != nil ||
		payload.Version != "1.0.0" || payload.Data.Service["executeLimit"] != "2" || payload.Data.Service["serviceTimeout"] != "500" ||
		payload.Data.Health["alarmWiseEyeScope"] != "scope" || len(payload.Data.Blocks) != 1 || payload.Data.Blocks[0].Image != "image" {
		t.Fatalf("unexpected dry run: %d %s %s", code, out, stderr)
	}
}
