package jupyter

import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"time"
	"unicode"

	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
	"github.com/mossexplore/platform-cli/cli-go/internal/platform"
)

const StudioPrefix = "/ai/backend/webstudio/dataExplorer/"

type StudioSelection struct {
	ID         string `json:"envId"`
	Name       string `json:"labelName"`
	Region     string `json:"region"`
	SelectedAt string `json:"selectedAt"`
}

func StudioStatus(paths localstate.Paths, cfg localstate.Config, api *platform.API) (StudioSelection, error) {
	if cfg.Profile().Jupyter.Mode != "webstudio" {
		return StudioSelection{}, errors.New("此操作需要当前环境 jupyter.mode=webstudio")
	}
	var selection StudioSelection
	data, err := os.ReadFile(studioPath(paths, cfg, api))
	if errors.Is(err, os.ErrNotExist) {
		return selection, errors.New("当前上下文未选择 Web Studio，请先执行 ml webstudio login ENV_ID")
	}
	if err != nil || json.Unmarshal(data, &selection) != nil || selection.ID == "" {
		return selection, errors.New("Web Studio 默认实例记录无效")
	}
	return selection, nil
}

func studioPath(paths localstate.Paths, cfg localstate.Config, api *platform.API) string {
	profile := cfg.Profile()
	binding, _ := json.Marshal([]any{paths.Config(), profile.Name, profile.Endpoint, profile.Jupyter.ServerURL, profile.Jupyter.Gateways,
		api.Username(), api.BusinessID()})
	return filepath.Join(paths.Dir, "webstudio", fmt.Sprintf("%x.json", sha256.Sum256(binding)))
}

func StudioLogin(ctx context.Context, api *platform.API, paths localstate.Paths, cfg localstate.Config, id string) error {
	client, err := openStudio(ctx, api, paths, cfg, id, true)
	if err != nil {
		return err
	}
	defer client.Close()
	return nil
}

func openStudio(ctx context.Context, api *platform.API, paths localstate.Paths, cfg localstate.Config, id string, persist bool) (*Client, error) {
	settings := cfg.Profile().Jupyter
	if settings.Mode != "webstudio" || settings.BusinessFile != "" {
		return nil, errors.New("Web Studio 连接需要配置 jupyter.mode=webstudio，且使用当前平台业务")
	}
	if settings.Gateways == nil {
		if _, err := gateway(settings.ServerURL); err != nil {
			return nil, err
		}
	} else {
		if len(settings.Gateways) == 0 {
			return nil, errors.New("jupyter.server_urls_by_region 必须为非空对象")
		}
		for _, address := range settings.Gateways {
			if _, err := gateway(address); err != nil {
				return nil, err
			}
		}
	}
	if id == "" {
		selection, err := StudioStatus(paths, cfg, api)
		if err != nil {
			return nil, err
		}
		id = selection.ID
	}
	list, err := api.JSON(ctx, http.MethodPost, StudioPrefix+"queryEnvList", nil, StudioListBody(api.BusinessID(), "", "", "", id, 1, 10))
	if err != nil {
		return nil, err
	}
	result, err := platform.Result(list, "查询 Web Studio 实例", false)
	if err != nil {
		return nil, err
	}
	var items []platform.Record
	if json.Unmarshal(result["envs"], &items) != nil || items == nil {
		return nil, errors.New("Web Studio 列表缺少有效的 envs")
	}
	var instance platform.Record
	for _, item := range items {
		if item.Text("envId") != id {
			continue
		}
		if instance != nil {
			return nil, errors.New("当前业务下未找到唯一匹配的 Web Studio")
		}
		instance = item
	}
	if instance == nil || instance["businessId"] != nil && instance.Text("businessId") != api.BusinessID() {
		return nil, errors.New("当前业务下未找到匹配的 Web Studio")
	}
	if instance.Text("status") != "online" {
		return nil, errors.New("Web Studio 当前不是 online 状态")
	}
	server := settings.ServerURL
	region := instance.Text("region")
	if settings.Gateways != nil {
		server = settings.Gateways[region]
		if server == "" {
			return nil, errors.New("Web Studio 实例区域未配置 Jupyter 网关")
		}
	}
	if err := api.CheckTarget(); err != nil {
		return nil, err
	}
	access, err := api.JSON(ctx, http.MethodPost, StudioPrefix+"accessUrl", nil,
		map[string]string{"businessId": api.BusinessID(), "envId": id, "operator": api.Username()})
	if err != nil {
		return nil, err
	}
	reply, err := platform.Result(access, "获取 Web Studio 访问地址", false)
	if err != nil {
		return nil, err
	}
	root, token, err := parseStudioAccess(server, reply.Text("accessUrl"))
	if err != nil {
		return nil, err
	}
	client, err := newClient(api, paths, cfg, root, token)
	if err != nil {
		return nil, err
	}
	client.studio = id
	if err := client.bootstrap(ctx); err != nil {
		client.Close()
		return nil, err
	}
	if persist {
		if _, err := client.JSON(ctx, http.MethodGet, "api/kernelspecs", nil, nil); err != nil {
			client.Close()
			return nil, err
		}
		selection := StudioSelection{ID: id, Name: instance.Text("labelName"), Region: region,
			SelectedAt: time.Now().In(time.FixedZone("Asia/Shanghai", 8*60*60)).Format("2006-01-02 15:04:05")}
		if err := saveStudio(paths, cfg, api, selection); err != nil {
			client.Close()
			return nil, err
		}
	}
	return client, nil
}

func saveStudio(paths localstate.Paths, cfg localstate.Config, api *platform.API, selection StudioSelection) error {
	unlock, err := paths.LockState()
	if err != nil {
		return err
	}
	defer unlock()
	if err := api.CheckTarget(); err != nil {
		return err
	}
	data, err := json.Marshal(selection)
	if err != nil {
		return err
	}
	return localstate.WritePrivate(studioPath(paths, cfg, api), data)
}

func StudioListBody(id, name, status, relator, envID string, page, size int) map[string]any {
	body := map[string]any{}
	for _, key := range strings.Fields("beginTime endTime labelName region scene subScene teamId status clusterType relator clusterName envId") {
		body[key] = ""
	}
	body["pageIndex"], body["pageSize"], body["businessId"] = page, size, id
	body["labelName"], body["status"], body["relator"], body["envId"] = name, status, relator, envID
	return body
}

func gateway(input string) (*url.URL, error) {
	address, err := url.Parse(input)
	if err != nil || strings.IndexFunc(input, unicode.IsSpace) >= 0 || address.User != nil || address.Hostname() == "" ||
		address.RawQuery != "" || address.ForceQuery || address.Fragment != "" || address.Path != "" && address.Path != "/" ||
		address.Scheme != "https" && address.Scheme != "http" {
		return nil, errors.New("Jupyter 网关须是不含路径、凭据、查询或片段的 HTTP(S) 地址")
	}
	return address, nil
}

func parseStudioAccess(server, raw string) (string, string, error) {
	root, err := gateway(server)
	if err != nil {
		return "", "", err
	}
	access, err := url.Parse(raw)
	invalid := errors.New("Web Studio 访问地址无效，请核对网关、/lab 路径和 token 参数")
	if err != nil || access.User != nil || access.Fragment != "" || strings.HasPrefix(raw, "//") ||
		strings.IndexFunc(raw, unicode.IsSpace) >= 0 {
		return "", "", invalid
	}
	if access.IsAbs() && (access.Scheme != root.Scheme || !strings.EqualFold(access.Hostname(), root.Hostname()) ||
		effectivePort(access) != effectivePort(root)) {
		return "", "", invalid
	}
	path := strings.TrimRight(access.Path, "/")
	if !strings.HasPrefix(path, "/") || !strings.HasSuffix(path, "/lab") || path == "/lab" ||
		strings.ContainsAny(path, "\\%") || strings.Contains(path, "//") || strings.IndexFunc(path, unicode.IsControl) >= 0 {
		return "", "", invalid
	}
	for _, segment := range strings.Split(path, "/") {
		if segment == "." || segment == ".." {
			return "", "", invalid
		}
	}
	query, err := url.ParseQuery(access.RawQuery)
	tokens := query["token"]
	if err != nil || len(tokens) != 1 || len(query) != 1 || strings.IndexFunc(tokens[0], unicode.IsControl) >= 0 {
		return "", "", invalid
	}
	root.Path, root.RawPath = strings.TrimSuffix(path, "/lab")+"/", ""
	return root.String(), tokens[0], nil
}

func effectivePort(address *url.URL) string {
	if port := address.Port(); port != "" {
		return port
	}
	if address.Scheme == "https" {
		return "443"
	}
	return "80"
}
