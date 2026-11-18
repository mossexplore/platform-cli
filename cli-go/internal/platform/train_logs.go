package platform

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/url"
	"strings"
)

var ErrLogNotReady = errors.New("日志未就绪")

func (a *API) RunningLogArchives(ctx context.Context, taskID, jobID string) ([]Record, error) {
	task, err := a.TrainTask(ctx, taskID)
	if err != nil {
		return nil, err
	}
	instances, err := a.AllTrainInstances(ctx, task)
	if err != nil {
		return nil, err
	}
	var job Record
	for _, instance := range instances {
		if instance.Text("jobId") == jobID {
			job = instance
			break
		}
	}
	if job == nil || job.Text("taskId") != taskID || job.Text("businessId") != a.BusinessID() {
		return nil, errors.New("执行实例不存在或与当前任务及业务不一致")
	}
	result, err := a.runningLog(ctx, "getRunJobLogArchiveList", job, []string{"businessId", "jobId", "taskId"}, nil, true)
	if err != nil {
		return nil, err
	}
	var count *int
	var entries []Record
	if json.Unmarshal(result["count"], &count) != nil || count == nil || json.Unmarshal(result["logInfoList"], &entries) != nil ||
		entries == nil || len(entries) != *count {
		return nil, errors.New("归档日志列表或数量异常")
	}
	for _, entry := range entries {
		if entry.Text("taskId") != taskID || entry.Text("jobId") != jobID || entry.Text("businessId") != a.BusinessID() || strings.TrimSpace(entry.Text("taskName")) == "" {
			return nil, errors.New("归档日志记录与执行实例不一致")
		}
	}
	return entries, nil
}

func (a *API) RunningLogURL(ctx context.Context, item Record) (string, error) {
	if string(item["status"]) != "1" {
		return "", errors.New("日志尚未归档成功")
	}
	result, err := a.runningLog(ctx, "getRunningJobLogUrl", item,
		[]string{"businessId", "taskId", "jobId", "roleJobId", "archiveId", "createUser"},
		map[string]any{"isApplicantPromise": true, "isUpload": false}, false)
	if err != nil {
		return "", err
	}
	return result.Text("downloadUrl"), nil
}

func (a *API) runningLog(ctx context.Context, route string, record Record, keys []string, extra map[string]any, archive bool) (Record, error) {
	if record.Text("businessId") != a.BusinessID() || strings.TrimSpace(record.Text("taskName")) == "" {
		return nil, errors.New("日志记录与当前业务不一致或缺少任务名称")
	}
	fields := map[string]string{}
	for _, key := range keys {
		value := record.Text(key)
		if strings.TrimSpace(value) == "" {
			return nil, fmt.Errorf("日志记录缺少有效的 %s", key)
		}
		fields[key] = value
	}
	body := trainEvent(fields)
	if len(extra) != 0 {
		data := map[string]any{}
		for key, value := range fields {
			data[key] = value
		}
		for key, value := range extra {
			data[key] = value
		}
		body["data"] = data
	}
	body["eventTarget"] = record.Text("taskName")
	request := a.JSON
	if archive {
		request = a.Mutation
	}
	payload, err := request(ctx, http.MethodPost, "/ai/backend/mtp/train/"+route, nil, body)
	if err != nil {
		return nil, err
	}
	return Result(payload, "获取执行实例日志", false)
}

func (a *API) HistoryLogURL(ctx context.Context, taskID, jobID, roleID string, plog bool) (string, error) {
	query := url.Values{"businessId": {a.BusinessID()}, "jobId": {jobID}}
	if roleID != "" {
		query.Set("roleJobId", roleID)
	}
	request := func(action string) (Record, error) {
		payload, err := a.JSON(ctx, http.MethodGet, trainInstancePrefix+action, query, nil)
		if err != nil {
			return nil, err
		}
		return Result(payload, action, false)
	}
	if !plog {
		value, err := request("queryJobLogIsExist")
		if err != nil {
			return "", err
		}
		switch {
		case string(value["isExistLog"]) == "true":
		case string(value["isExistLog"]) == "false" || string(value["failedUploadSwitch"]) == "false":
			return "", ErrLogNotReady
		default:
			return "", errors.New("日志状态未明确")
		}
	}
	query.Set("taskId", taskID)
	query.Set("isApplicantPromise", "true")
	if plog {
		data, err := request("downloadPlog")
		if err != nil {
			return "", err
		}
		return data.Text("plogUrl"), nil
	}
	data, err := request("downloadLogUrl")
	if err != nil {
		return "", err
	}
	if string(data["failedUploadSwitch"]) == "false" {
		return "", ErrLogNotReady
	}
	return data.Text("url"), nil
}

func (a *API) ArchiveHistoryLog(ctx context.Context, jobID string) error {
	_, err := a.trainMutation(ctx, trainInstancePrefix+"manualArchiveLog", trainEvent(map[string]string{
		"businessId": a.BusinessID(), "jobId": jobID,
	}), "手动归档", false)
	return err
}

func HasPlog(record Record) bool {
	var parsed Record
	if json.Unmarshal([]byte(record.Text("sysParam")), &parsed) != nil {
		return false
	}
	return parsed.Text("plogUploadSuccess") == "1"
}
