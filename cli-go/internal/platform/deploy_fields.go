package platform

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"math/big"
	"strconv"
	"strings"
)

func nullField(raw json.RawMessage) bool  { return len(raw) == 0 || string(raw) == "null" }
func emptyField(raw json.RawMessage) bool { return nullField(raw) || string(raw) == `""` }
func rawArray(raw json.RawMessage) bool   { return len(raw) > 0 && raw[0] == '[' && json.Valid(raw) }

func mappedDeploy(source Record, fields map[string]string, defaults map[string]any) (map[string]any, error) {
	data := make(map[string]any)
	for target, field := range fields {
		raw := source[field]
		fallback, optional := defaults[field]
		if nullField(raw) {
			if !optional {
				return nil, fmt.Errorf("部署配置缺少必填字段 %s", field)
			}
			data[target] = fallback
			continue
		}
		if _, requiresText := fallback.(string); requiresText && raw[0] != '"' {
			return nil, fmt.Errorf("%s 必须为字符串", field)
		}
		data[target] = raw
	}
	return data, nil
}

func serviceDeployFields(model, template Record, options DeployOptions) (map[string]any, error) {
	fields, err := mappedDeploy(template, map[string]string{"inferenceType": "inferenceType", "env": "env"}, nil)
	if err != nil {
		return nil, err
	}
	update := map[string]string{"rolling": "1", "in-place": "0"}[options.UpdateMode]
	if update == "" {
		return nil, errors.New("更新模式不合法")
	}
	for _, key := range []string{"modelId", "modelName", "modelVersion"} {
		if emptyField(model[key]) {
			return nil, fmt.Errorf("部署配置缺少必填字段 %s", key)
		}
	}
	for _, key := range []string{"inferenceType", "env"} {
		if emptyField(template[key]) {
			return nil, fmt.Errorf("部署配置缺少必填字段 %s", key)
		}
	}
	timeout, limit := template["serviceTimeout"], template["executeLimit"]
	if options.Timeout != nil {
		timeout = json.RawMessage(strconv.Itoa(*options.Timeout))
	}
	if options.Limit != nil {
		limit = json.RawMessage(strconv.Quote(strconv.Itoa(*options.Limit)))
	}
	if emptyField(timeout) || emptyField(limit) {
		command := fmt.Sprintf("ml model deploy %s --template %s", model.Text("modelId"), template.Text("deployTemplateId"))
		if emptyField(timeout) {
			command += " --service-timeout TIMEOUT_MS"
		}
		if emptyField(limit) {
			command += " --execute-limit MAX_CONCURRENT_REQUESTS"
		}
		return nil, fmt.Errorf("部署模板缺少超时或并发数，请填写参数后重试\n命令格式：%s", command)
	}
	if _, err := deployInteger(timeout, "serviceTimeout", 1); err != nil {
		return nil, err
	}
	if _, err := deployInteger(limit, "executeLimit", 0); err != nil {
		return nil, err
	}
	fields["serviceId"], fields["serviceName"], fields["serviceVersion"] = nil, model["modelName"], model["modelVersion"]
	fields["serviceTimeout"], fields["executeLimit"], fields["updateMode"] = timeout, limit, update
	if options.QPS != nil {
		if *options.QPS < 1 {
			return nil, errors.New("qps 必须为正整数")
		}
		fields["requestLimit"] = *options.QPS
	}
	return fields, nil
}

func deployHealth(template Record, scope string, opts DeployOptions) (map[string]any, error) {
	mode := map[string]string{"default": "Default", "response-code": "RespCodeMatch", "response-code-and-data": "RespCodeAndDataMatch"}[opts.HealthMode]
	if mode == "" || opts.HealthPort < 1 || opts.HealthPort > 65535 {
		return nil, errors.New("健康检查模式或端口不合法")
	}
	result := map[string]any{"healthCheckTypeInContainer": mode, "healthPort": strconv.Itoa(opts.HealthPort), "alarmWiseEyeScope": scope}
	for _, field := range []struct {
		target, source, fallback string
		minimum                  int
		integer                  bool
	}{
		{"healthCheckTimeout", "healthCheckTimeout", "5", 1, true}, {"startTimeout", "startTimeOut", "120", 1, true},
		{"initialDelaySeconds", "initialDelaySeconds", "120", 0, true}, {"periodSeconds", "periodSeconds", "10", 1, true},
		{"failureThreshold", "failureThreshold", "3", 1, true}, {"healthPath", "healthPath", "health", 0, false}, {"healthType", "healthType", "httpGet", 0, false},
	} {
		raw := template[field.source]
		if emptyField(raw) {
			raw = json.RawMessage(strconv.Quote(field.fallback))
		}
		if field.integer {
			if _, err := deployInteger(raw, field.target, int64(field.minimum)); err != nil {
				return nil, err
			}
		}
		result[field.target] = deployText(raw)
	}
	grace := template["terminationGracePeriodSeconds"]
	if emptyField(grace) {
		grace = json.RawMessage("10")
	}
	value, err := deployInteger(grace, "terminationGracePeriodSeconds", 0)
	if err != nil {
		return nil, err
	}
	result["terminationGracePeriodSeconds"] = value
	return result, nil
}

func deployBlock(id string, resource, framework Record) (map[string]any, error) {
	block, err := mappedDeploy(resource, map[string]string{
		"quotaType": "quotaType", "templateId": "containerSpec", "clusterName": "clusterName",
		"imageName": "appImageName", "imageVersion": "imageTag", "sfsLocation": "sfsLocation", "customStartupCommand": "customStartupCommand",
	}, map[string]any{"sfsLocation": "", "customStartupCommand": ""})
	if err != nil {
		return nil, err
	}
	for _, key := range []string{"quotaType", "containerSpec", "clusterName", "appImageName", "imageTag", "frameworkPkgId", "cpu"} {
		if emptyField(resource[key]) {
			return nil, fmt.Errorf("部署配置缺少必填字段 %s", key)
		}
	}
	infer, err := mappedDeploy(framework, map[string]string{"inferFrameObjectId": "pkgStorageId", "inferFrameBucketId": "pkgStorageLocation",
		"inferFrameStoreType": "storageType"}, nil)
	if err != nil {
		return nil, err
	}
	for _, key := range []string{"pkgStorageId", "pkgStorageLocation", "storageType"} {
		if emptyField(framework[key]) {
			return nil, fmt.Errorf("推理框架缺少必填字段 %s", key)
		}
	}
	raw := resource["frameworkConfiguration"]
	if bytes.HasPrefix(raw, []byte(`"`)) {
		raw = json.RawMessage(resource.Text("frameworkConfiguration"))
	}
	var config Record
	if json.Unmarshal(raw, &config) != nil || len(config) == 0 {
		return nil, errors.New("frameworkConfiguration 必须为非空 JSON 对象")
	}
	infer["inferFrameId"], infer["configuration"] = resource["frameworkPkgId"], raw
	memory, ok := strings.CutSuffix(resource.Text("memory"), "G")
	if value, parsed := deployNumber(memory); !ok || !parsed || value.Sign() <= 0 {
		return nil, errors.New("memory 必须为以 G 为单位的正数")
	}
	require := map[string]any{"cpu": resource["cpu"], "memory": memory, "replicas": "1"}
	for _, key := range []string{"gpu", "npu"} {
		raw := resource[key]
		if emptyField(raw) {
			raw = json.RawMessage(`"0"`)
		}
		if _, err := deployInteger(raw, key, 0); err != nil {
			return nil, err
		}
		require[key] = raw
	}
	block["resourceDockerId"], block["resourceRequire"], block["inferFramework"] = id, require, infer
	block["sfsReplicas"], block["volumes"], block["blockName"] = []any{}, []any{}, ""
	block["description"], block["swrInstanceId"], block["elasticConfig"] = nil, nil, nil
	for _, key := range []string{"hostLabels", "hostIpNames", "envs", "args"} {
		raw := resource[key]
		if nullField(raw) {
			raw = json.RawMessage("[]")
		}
		if !rawArray(raw) {
			return nil, fmt.Errorf("%s 必须为数组", key)
		}
		block[key] = raw
	}
	return block, nil
}

func deployText(raw json.RawMessage) string {
	if len(raw) > 0 && raw[0] == '"' {
		var text string
		_ = json.Unmarshal(raw, &text)
		return text
	}
	return string(raw)
}

func deployNumber(raw string) (*big.Rat, bool) {
	if strings.Contains(raw, "/") {
		return nil, false
	}
	return new(big.Rat).SetString(strings.TrimSpace(raw))
}

func deployInteger(raw json.RawMessage, field string, minimum int64) (int64, error) {
	value, ok := deployNumber(deployText(raw))
	if !ok || !value.IsInt() || !value.Num().IsInt64() || value.Num().Int64() < minimum {
		return 0, fmt.Errorf("%s 必须为不小于 %d 的整数", field, minimum)
	}
	return value.Num().Int64(), nil
}
