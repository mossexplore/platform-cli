package platform

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"strings"
)

func (a *API) StartTrain(ctx context.Context, taskID string) (string, error) {
	result, err := a.trainMutation(ctx, trainPrefix+"startScheduleTask",
		trainEvent(map[string]string{"taskId": taskID}), "训练任务执行", true)
	return result.Object("data").Text("jobId"), err
}

func (a *API) DeleteTrain(ctx context.Context, task Record) error {
	team, err := trainTeam(task)
	if err != nil {
		return err
	}
	if strings.TrimSpace(task.Text("taskId")) == "" || strings.TrimSpace(task.Text("taskName")) == "" {
		return errors.New("训练任务缺少有效的 taskId 或 taskName")
	}
	_, err = a.trainMutation(ctx, trainPrefix+"v2/delete", map[string]any{
		"taskId": task.Text("taskId"), "teamId": team,
		"target": task.Text("taskName"), "softDeleteFlag": true,
	}, "删除训练任务", false)
	return err
}

func trainTeam(task Record) (string, error) {
	var team *string
	if json.Unmarshal(task["teamId"], &team) != nil || team == nil {
		return "", errors.New("训练任务缺少有效的 teamId")
	}
	return *team, nil
}

func (a *API) CloneTrainDetail(ctx context.Context, task Record) (Record, error) {
	team, err := trainTeam(task)
	if err != nil {
		return nil, err
	}
	return a.TrainDetail(ctx, task.Text("taskId"), team, false)
}

func (a *API) CloneTrain(ctx context.Context, detail Record, name string, config *string) (string, error) {
	info := detail.Object("taskInfo")
	base := info.Object("baseInfo")
	if base == nil {
		return "", errors.New("训练任务详情缺少有效的 taskInfo.baseInfo")
	}
	if err := base.Put("taskName", name); err != nil {
		return "", err
	}
	if err := info.Put("baseInfo", base); err != nil {
		return "", err
	}
	if err := info.Put("createUser", a.Username()); err != nil {
		return "", err
	}
	if config != nil {
		if err := updateTrainParameters(info, *config); err != nil {
			return "", err
		}
	}
	if err := detail.Put("taskInfo", info); err != nil {
		return "", err
	}
	if err := detail.Put("name", name); err != nil {
		return "", err
	}
	result, err := a.trainMutation(ctx, trainPrefix+"createNew", map[string]any{"data": detail}, "克隆训练任务", false)
	return result.Object("data").Text("id"), err
}

func (a *API) UpdateTrainConfig(ctx context.Context, taskID, config string) error {
	detail, err := a.TrainDetail(ctx, taskID, "", true)
	if err != nil {
		return err
	}
	info := detail.Object("taskInfo")
	var name *string
	if info == nil || json.Unmarshal(detail["name"], &name) != nil || name == nil {
		return errors.New("训练任务详情缺少有效的 data.name 或 taskInfo")
	}
	if err := updateTrainParameters(info, config); err != nil {
		return err
	}
	if err := info.Put("updateUser", a.Username()); err != nil {
		return err
	}
	_, err = a.trainMutation(ctx, trainPrefix+"updateNew", map[string]any{"data": map[string]any{
		"id": taskID, "businessId": a.BusinessID(), "name": *name, "creator": "", "modifier": "", "taskInfo": info,
	}}, "更新训练任务自定义参数", true)
	return err
}

func updateTrainParameters(info Record, config string) error {
	params := info.Object("parameter")
	if params == nil {
		if raw := bytes.TrimSpace(info["parameter"]); len(raw) > 0 && !bytes.Equal(raw, []byte("null")) {
			return errors.New("训练任务详情的 taskInfo.parameter 不是对象")
		}
		params = Record{}
	}
	if err := params.Put("customizeConfig", config); err != nil {
		return err
	}
	return info.Put("parameter", params)
}

func (a *API) AllTrainInstances(ctx context.Context, task Record) ([]Record, error) {
	var items []Record
	seen := make(map[string]bool)
	for page := 1; ; page++ {
		result, err := a.TrainInstances(ctx, task, page, 10, "createTime")
		if err != nil {
			return nil, err
		}
		for _, item := range result.Items {
			id := item.Text("jobId")
			if strings.TrimSpace(id) == "" || strings.TrimSpace(item.Text("taskName")) == "" {
				return nil, errors.New("执行实例缺少有效的 jobId 或 taskName")
			}
			if seen[id] {
				return nil, fmt.Errorf("执行实例分页重复返回 jobId：%s", id)
			}
			seen[id] = true
			items = append(items, item)
		}
		if len(items) >= result.Count {
			return items, nil
		}
		if len(result.Items) == 0 {
			return nil, errors.New("执行实例分页提前结束，无法确认完整列表")
		}
	}
}

func (a *API) CancelTrainInstance(ctx context.Context, taskID string, item Record) (string, error) {
	body := trainEvent(map[string]string{"taskId": taskID, "jobId": item.Text("jobId")})
	body["eventTarget"] = item.Text("taskName")
	result, err := a.trainMutation(ctx, "/ai/backend/mtp/train/cancelMultiInstanceTask", body, "取消执行实例", false)
	return result.Text("des"), err
}

func (a *API) trainMutation(ctx context.Context, path string, body any, action string, strict bool) (Record, error) {
	payload, err := a.Mutation(ctx, http.MethodPost, path, nil, body)
	if err != nil {
		return nil, err
	}
	return Result(payload, action, strict)
}
