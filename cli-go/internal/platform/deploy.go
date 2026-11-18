package platform

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/url"
	"strings"

	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
)

const PublishPath = "/ai/backend/mep/services/rtcContainer/publish"

type DeployOptions struct {
	Timeout, Limit, QPS                          *int
	UpdateMode, HealthMode                       string
	HealthPort                                   int
	Description, RequestContent, ResponseContent string
}

func (a *API) PrepareDeploy(ctx context.Context, modelID, templateID string, options DeployOptions) (map[string]any, error) {
	entry, err := a.session.Paths.BusinessEntry(a.credentials)
	if err != nil {
		return nil, err
	}
	tenant := entry.Selected.TenantID
	if tenant == "" || entry.Selected.BusinessID != a.BusinessID() {
		return nil, errors.New("缺少当前业务对应的真实租户 ID")
	}
	post := func(path string, body any) (Record, error) {
		raw, err := a.JSON(ctx, http.MethodPost, path, nil, body)
		if err != nil {
			return nil, err
		}
		return Result(raw, "查询部署准备信息", false)
	}
	model, err := post("/ai/backend/mep/models/queryDetail", map[string]string{"modelId": modelID})
	if err != nil {
		return nil, err
	}
	if model.Text("modelId") != modelID {
		return nil, errors.New("模型详情 ID 与请求不一致")
	}
	result, err := post("/ai/backend/mep/scm/deploytemplate/queryDetail", map[string]string{"deployTemplateId": templateID})
	if err != nil {
		return nil, err
	}
	template := result.Object("template")
	if template.Text("deployTemplateId") != templateID {
		return nil, errors.New("部署模板详情 ID 与请求不一致")
	}
	service, err := serviceDeployFields(model, template, options)
	if err != nil {
		return nil, err
	}
	var names []string
	if json.Unmarshal(template["dockerResourceTemplate"], &names) != nil || len(names) == 0 ||
		strings.TrimSpace(template.Text("businessId")) == "" || strings.TrimSpace(template.Text("deployTemplateType")) == "" {
		return nil, errors.New("部署模板缺少关联资源名称、业务 ID 或模板类型")
	}
	blocks := []map[string]any{}
	frameworks := map[string]Record{}
	for _, name := range names {
		if strings.TrimSpace(name) == "" {
			return nil, errors.New("关联资源模板名称不能为空")
		}
		result, err := post("/ai/backend/mep/resourcetemp/queryList", map[string]string{
			"templateType": template.Text("deployTemplateType"), "businessId": template.Text("businessId"), "dockerResourceTemplateName": name,
		})
		if err != nil {
			return nil, err
		}
		var items []Record
		if json.Unmarshal(result["resourceTemplateInfoList"], &items) != nil || items == nil {
			return nil, errors.New("关联资源查询缺少有效的 resourceTemplateInfoList")
		}
		matches := []Record{}
		for _, item := range items {
			if item.Text("dockerResourceTemplateName") == name {
				matches = append(matches, item)
			}
		}
		if len(matches) != 1 {
			return nil, errors.New("部署模板关联资源缺失或名称不唯一，无法部署")
		}
		resourceID := matches[0].Text("dockerId")
		if strings.TrimSpace(resourceID) == "" {
			return nil, errors.New("关联资源缺少 dockerId")
		}
		resource, err := post("/ai/backend/mep/resourcetemp/queryDetail", map[string]string{"dockerId": resourceID})
		if err != nil {
			return nil, err
		}
		if resource.Text("dockerResourceTemplateName") != name {
			return nil, errors.New("资源模板详情名称与关联名称不一致")
		}
		packageID := resource.Text("frameworkPkgId")
		if strings.TrimSpace(packageID) == "" {
			return nil, errors.New("资源模板缺少 frameworkPkgId")
		}
		if frameworks[packageID] == nil {
			framework, err := post("/ai/backend/mep/scm/frameworkPkg/queryFrameworkPkgDetail", map[string]string{"frameworkPkgId": packageID})
			if err != nil {
				return nil, err
			}
			value := framework.Object("data")
			if strings.TrimSpace(value.Text("name")) == "" || strings.TrimSpace(value.Text("version")) == "" {
				return nil, errors.New("推理框架详情缺少有效名称或版本")
			}
			frameworks[packageID] = value
		}
		block, err := deployBlock(resourceID, resource, frameworks[packageID])
		if err != nil {
			return nil, err
		}
		blocks = append(blocks, block)
	}
	raw, err := a.JSON(ctx, http.MethodGet, "/ai/user/queryTenantDetail", url.Values{"businessId": {tenant}}, nil)
	if err != nil {
		return nil, err
	}
	detail, err := Result(raw, "查询真实租户", false)
	if err != nil {
		return nil, err
	}
	var entries []Record
	if json.Unmarshal(detail.Object("data")["tenantServiceEntityList"], &entries) != nil || len(entries) == 0 {
		return nil, errors.New("真实租户没有可用的 tenantServiceEntityList")
	}
	scope := entries[0].Text("serviceGroup")
	if strings.TrimSpace(scope) == "" {
		return nil, errors.New("真实租户首个 serviceGroup 无效")
	}
	return deployPayload(model, template, blocks, scope, service, options)
}

func deployPayload(model, template Record, blocks []map[string]any, scope string, service map[string]any, options DeployOptions) (map[string]any, error) {
	modelFields := map[string]string{
		"modelSource": "source", "modelSourceId": "sourceId", "modelSourceEnv": "sourceEnv", "modelTag": "modelTag",
		"modelId": "modelId", "modelPkgLocationReplicas": "modelHistoryList", "modelName": "modelName", "modelVersion": "modelVersion",
		"modelPkgId": "pkgId", "modelType": "modelType", "modelSize": "pkgSize", "modelPkgLocation": "pkgLocation",
		"businessId": "businessId", "teamId": "teamId", "storeType": "storeType", "tags": "tags",
	}
	modelInfo, err := mappedDeploy(model, modelFields, map[string]any{"sourceEnv": "", "teamId": "", "tags": []any{}, "modelHistoryList": []any{}})
	if err != nil {
		return nil, err
	}
	for _, key := range []string{"modelHistoryList", "tags"} {
		if raw := model[key]; !nullField(raw) && !rawArray(raw) {
			return nil, fmt.Errorf("%s 必须为数组", key)
		}
	}
	health, err := deployHealth(template, scope, options)
	if err != nil {
		return nil, err
	}
	components := []Record{}
	if raw := template["comptPkgInfoList"]; !nullField(raw) && (json.Unmarshal(raw, &components) != nil || components == nil) {
		return nil, errors.New("comptPkgInfoList 必须为对象数组")
	}
	packages := []map[string]any{}
	for _, component := range components {
		mapped, err := mappedDeploy(component, map[string]string{"comptPkgId": "comptPkgId", "comptPkgName": "name", "comptPkgVersion": "version",
			"nspPkgId": "nspPkgId", "nspPkgLocation": "nspPkgLocation", "businessId": "businessId", "comptPkgFileName": "comptPkgFileName"}, nil)
		if err != nil {
			return nil, err
		}
		packages = append(packages, mapped)
	}
	data := map[string]any{"modelInfo": modelInfo, "serviceInfo": service, "comptPkgs": packages, "extendConfiguration": health,
		"serviceBlocks": blocks, "serviceDocument": map[string]string{"description": options.Description, "requestContent": options.RequestContent, "responseContent": options.ResponseContent}}
	return map[string]any{
		"version": "1.0.0", "meta": map[string]string{"uuid": localstate.NewID()}, "data": data,
		"eFlowInfo": map[string]any{"actionType": "service_publish", "modelInfoList": []map[string]any{{"modelName": model["modelName"], "modelVersion": model["modelVersion"]}}},
	}, nil
}
