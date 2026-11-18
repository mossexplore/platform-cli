package platform

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"strings"

	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
)

const trainPrefix = "/ai/backend/modelDev/modelTrain/"
const trainInstancePrefix = "/ai/backend/mtp/traintask/"

type Record map[string]json.RawMessage

func (record Record) Text(key string) string {
	var value string
	_ = json.Unmarshal(record[key], &value)
	return value
}

func (record Record) Object(key string) Record {
	var value Record
	_ = json.Unmarshal(record[key], &value)
	return value
}

func (record Record) Put(key string, value any) error {
	encoded, err := json.Marshal(value)
	if err == nil {
		record[key] = encoded
	}
	return err
}

func Result(payload json.RawMessage, action string, requireDescription bool) (Record, error) {
	var envelope struct {
		Result Record `json:"result"`
	}
	if json.Unmarshal(payload, &envelope) != nil || envelope.Result == nil {
		return nil, fmt.Errorf("%s失败：响应缺少 result", action)
	}
	var code *int
	if json.Unmarshal(envelope.Result["code"], &code) != nil || code == nil || *code != 0 ||
		requireDescription && envelope.Result.Text("des") != "success" {
		return nil, fmt.Errorf("%s失败：服务端未确认成功", action)
	}
	return envelope.Result, nil
}

type Page struct {
	Count     int      `json:"count"`
	PageIndex int      `json:"pageIndex"`
	PageSize  int      `json:"pageSize"`
	Items     []Record `json:"items"`
}

func trainPage(source Record, field string, page, size int, allowOmittedEmpty bool) (Page, error) {
	value := Page{PageIndex: page, PageSize: size, Items: []Record{}}
	var count *int
	if json.Unmarshal(source["count"], &count) != nil || count == nil || *count < 0 {
		return value, errors.New("查询响应缺少有效的 count")
	}
	value.Count = *count
	if value.Count == 0 && allowOmittedEmpty {
		return value, nil
	}
	if json.Unmarshal(source[field], &value.Items) != nil || value.Items == nil {
		return value, fmt.Errorf("查询响应缺少有效的 %s 数组", field)
	}
	for _, record := range value.Items {
		if record == nil {
			return value, fmt.Errorf("查询响应中的 %s 包含无效记录", field)
		}
	}
	return value, nil
}

func (a *API) TrainList(ctx context.Context, page, size int, name string) (Page, error) {
	mlops := a.PlatformType() == "mlops"
	if page < 1 || size < 1 || mlops && size > 200 {
		return Page{}, errors.New("page 或 page-size 超出有效范围")
	}
	data := map[string]any{
		"taskName": name, "taskType": nil, "taskType1": "mtp-all", "businessId": a.BusinessID(),
		"category": "mtp-all", "tags": nil, "pageIndex": page, "pageSize": size,
	}
	for _, field := range strings.Fields("cronFlag depTask scene subScene teamId noRunDays createUser updateUser trainEngine trainMode distFramework isDeleted region scope inputName algorithmName algoInputName algorithmVersion taskOwner imagePackageId bucketName inputTaskId taskStr customLabels taskId") {
		data[field] = ""
	}
	for _, field := range []string{"noticeTime", "updateNoticeTime", "jobStatus", "taskTags"} {
		data[field] = []string{}
	}
	for _, field := range []string{"private", "baseInfo", "external", "sharing", "running", "excludeSpecFlag"} {
		data[field] = false
	}
	for _, field := range []string{"beginTime", "endTime", "updateBeginTime", "updateEndTime"} {
		data[field] = nil
	}
	path, body := trainPrefix+"list", any(map[string]any{"data": data})
	if mlops {
		path, body = trainInstancePrefix+"queryList", data
		for _, field := range []string{"inputJobId", "jobStr", "jobId"} {
			data[field] = ""
		}
	} else {
		data["reverseTaskTags"], data["reverseTags"] = []string{}, []string{}
	}
	payload, err := a.JSON(ctx, http.MethodPost, path, nil, body)
	if err != nil {
		return Page{}, err
	}
	result, err := Result(payload, "查询训练任务", false)
	if err != nil {
		return Page{}, err
	}
	if !mlops {
		result = result.Object("data")
	}
	return trainPage(result, "taskInfos", page, size, mlops)
}

func findTrainRecord(ctx context.Context, id, key string, query func(context.Context, int) (Page, error)) (Record, error) {
	seen := make(map[string]bool)
	for page := 1; ; page++ {
		result, err := query(ctx, page)
		if err != nil {
			return nil, err
		}
		newItems := false
		for _, item := range result.Items {
			value := item.Text(key)
			if value == id {
				return item, nil
			}
			if value != "" && !seen[value] {
				seen[value] = true
				newItems = true
			}
		}
		if len(result.Items) == 0 || page > (result.Count-1)/result.PageSize {
			return nil, fmt.Errorf("当前业务下未找到 %s %s", key, id)
		}
		if !newItems {
			return nil, errors.New("分页未返回新记录，无法确认查找结果")
		}
	}
}

func (a *API) TrainTask(ctx context.Context, taskID string) (Record, error) {
	return findTrainRecord(ctx, taskID, "taskId", func(ctx context.Context, page int) (Page, error) {
		return a.TrainList(ctx, page, 10, "")
	})
}

func (a *API) TrainDetail(ctx context.Context, taskID, teamID string, strict bool) (Record, error) {
	payload, err := a.JSON(ctx, http.MethodPost, trainPrefix+"detailNew", nil,
		map[string]any{"data": map[string]string{"id": taskID, "businessId": a.BusinessID(), "teamId": teamID}})
	if err != nil {
		return nil, err
	}
	result, err := Result(payload, "获取训练任务详情", strict)
	if err != nil {
		return nil, err
	}
	detail := result.Object("data")
	if detail == nil {
		return nil, errors.New("训练任务详情缺少有效的 result.data")
	}
	return detail, nil
}

func (a *API) TrainInstances(ctx context.Context, task Record, page, size int, sortField string) (Page, error) {
	for _, field := range []string{"taskId", "businessId", "taskType"} {
		if strings.TrimSpace(task.Text(field)) == "" {
			return Page{}, fmt.Errorf("训练任务缺少有效的 %s", field)
		}
	}
	body := map[string]any{
		"taskId": task.Text("taskId"), "businessId": task.Text("businessId"), "jobType": task.Text("taskType"),
		"pageIndex": page, "pageSize": size, "sortField": sortField, "sortOrder": "ascend",
	}
	return a.trainJobPage(ctx, "queryJobInstanceByTaskId", page, size, body)
}

func (a *API) TrainHistory(ctx context.Context, taskID string, page, size int) (Page, error) {
	body := map[string]any{
		"taskId": taskID, "pageIndex": page, "pageSize": size,
		"sortField": "statusTime", "sortOrder": "ascend", "source": "history", "latestFlag": "true", "status": []string{},
	}
	return a.trainJobPage(ctx, "queryScheduleTaskList", page, size, body)
}

func (a *API) trainJobPage(ctx context.Context, action string, page, size int, body map[string]any) (Page, error) {
	if page < 1 || size < 1 || size > 200 {
		return Page{}, errors.New("page 必须大于等于 1，page-size 必须为 1 到 200")
	}
	payload, err := a.JSON(ctx, http.MethodPost, trainInstancePrefix+action, nil, body)
	if err != nil {
		return Page{}, err
	}
	result, err := Result(payload, "查询执行记录", false)
	if err != nil {
		return Page{}, err
	}
	return trainPage(result, "jobs", page, size, false)
}

func (a *API) TrainHistoryRecord(ctx context.Context, taskID, jobID string) (Record, error) {
	return findTrainRecord(ctx, jobID, "jobId", func(ctx context.Context, page int) (Page, error) {
		return a.TrainHistory(ctx, taskID, page, 200)
	})
}

func trainEvent(data map[string]string) map[string]any {
	return map[string]any{
		"version": "1.0", "meta": map[string]string{"uuid": localstate.NewID()}, "data": data,
	}
}
