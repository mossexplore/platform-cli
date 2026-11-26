package command

import (
	"encoding/json"
	"fmt"
	"io"
	"math"
	"strconv"
	"strings"
	"time"

	"github.com/mossexplore/platform-cli/cli-go/internal/output"
	"github.com/mossexplore/platform-cli/cli-go/internal/platform"
)

type recordColumn struct{ title, key string }

var trainTaskColumns = []recordColumn{
	{"任务 ID", "taskId"}, {"任务名称", "taskName"}, {"任务类型", "taskType"}, {"业务场景", "scene"}, {"修改者", "updateUser"},
	{"更新时间", "updateTime"}, {"最新执行时间", "latestRunTime"}, {"大小", "fileSize"}, {"描述", "description"},
}

var trainInstanceColumns = []recordColumn{
	{"作业ID", "jobId"}, {"算法名称", "algorithmName"}, {"CPU", "cpuSize"}, {"GPU", "gpuSize"}, {"内存", "memorySize"},
	{"状态", "status"}, {"执行节点", "hostIp"}, {"集群", "poolName"}, {"触发方式", "actionType"}, {"开始时间", "createTime"},
	{"存储桶", "bucketName"}, {"执行时长", "runningTime"}, {"排队时长", "queueTime"}, {"配额等待时间", "waitTime"},
}

var trainHistoryColumns = []recordColumn{
	{"作业ID", "jobId"}, {"算法名称", "algorithmName"}, {"CPU", "cpuSize"}, {"GPU", "gpuSize"}, {"内存", "memorySize"},
	{"状态", "status"}, {"集群", "poolName"}, {"节点数", "infraSize"}, {"大小", "fileSize"}, {"检查时间", "checkTime"},
	{"开始时间", "createTime"}, {"结束时间", "statusTime"}, {"触发方式", "actionType"}, {"存储桶", "bucketName"},
	{"执行时长", "runningTime"}, {"排队时长", "queueTime"}, {"配额等待时间", "waitTime"},
}

var trainRoles = []recordColumn{
	{"角色作业 ID", "roleJobId"}, {"名称", "roleType"}, {"算法名称", "algorithmName"}, {"状态", "status"},
	{"节点数", "infraSize"}, {"CPU", "cpuSize"}, {"GPU", "gpuSize"}, {"内存", "memorySize"},
	{"执行节点", "hostIp"}, {"开始时间", "createTime"},
}

var trainStatus = map[string]string{
	"FAILED": "执行失败", "COMPLETED": "执行完成", "CANCELED": "取消", "TIMEOUT": "超时", "LACK_RESOURCE": "资源不足",
}

var beijing = time.FixedZone("Asia/Shanghai", 8*60*60)

func fieldText(raw json.RawMessage) string {
	if len(raw) == 0 || string(raw) == "null" || string(raw) == `""` {
		return "-"
	}
	if raw[0] == '"' {
		var text string
		if json.Unmarshal(raw, &text) == nil {
			return text
		}
	}
	return string(raw)
}

func dateText(raw json.RawMessage) string {
	if date, ok := recordTime(raw); ok {
		return date.In(beijing).Format("2006-01-02 15:04:05")
	}
	return fieldText(raw)
}

func recordTime(raw json.RawMessage) (time.Time, bool) {
	value := fieldText(raw)
	if millis, err := strconv.ParseFloat(value, 64); err == nil && !math.IsInf(millis, 0) && !math.IsNaN(millis) {
		return time.UnixMilli(int64(millis)), true
	}
	value = strings.Replace(value, " ", "T", 1)
	if date, err := time.Parse(time.RFC3339Nano, value); err == nil {
		return date, true
	}
	if date, err := time.ParseInLocation("2006-01-02T15:04:05", value, beijing); err == nil {
		return date, true
	}
	return time.Time{}, false
}

func trainValue(record platform.Record, key string) string {
	raw := record[key]
	text := fieldText(raw)
	switch key {
	case "updateTime", "latestRunTime", "checkTime", "createTime", "statusTime":
		return dateText(raw)
	case "runningTime", "queueTime", "waitTime", "fileSize":
		number, err := strconv.ParseFloat(text, 64)
		if err != nil || number < 0 {
			return text
		}
		if key == "fileSize" {
			switch {
			case number >= 1<<30:
				return fmt.Sprintf("%.2fG", number/(1<<30))
			case number >= 1<<20:
				return fmt.Sprintf("%.2fM", number/(1<<20))
			case number >= 1<<10:
				return fmt.Sprintf("%.2fK", number/(1<<10))
			default:
				return fmt.Sprintf("%gB", number)
			}
		}
		seconds := ""
		if key == "waitTime" {
			seconds = fmt.Sprintf("%gs", math.Mod(number, 60))
			number = math.Floor(number / 60)
			if number == 0 {
				return seconds
			}
		}
		days, hours := math.Floor(number/1440), math.Floor(math.Mod(number, 1440)/60)
		duration := fmt.Sprintf("%gmin%s", math.Mod(number, 60), seconds)
		if days > 0 || hours > 0 {
			duration = fmt.Sprintf("%gh%s", hours, duration)
		}
		if days > 0 {
			duration = fmt.Sprintf("%gday%s", days, duration)
		}
		return duration
	}
	return text
}

func renderRecordTable(out io.Writer, columns []recordColumn, records []platform.Record, value func(platform.Record, string) string) error {
	headers := make([]string, 0, len(columns))
	for _, column := range columns {
		headers = append(headers, column.title)
	}
	rows := make([][]string, 0, len(records))
	for _, record := range records {
		row := make([]string, 0, len(columns))
		for _, column := range columns {
			row = append(row, value(record, column.key))
		}
		rows = append(rows, row)
	}
	return output.Table(out, headers, rows)
}

func renderTrainHistoryLogRoles(out io.Writer, roles []platform.Record) error {
	headers := []string{"编号", "roleJobId"}
	for _, column := range trainRoles[1:] {
		headers = append(headers, column.title)
	}
	rows := make([][]string, 0, len(roles))
	for i, role := range roles {
		row := []string{strconv.Itoa(i + 1)}
		for _, column := range trainRoles {
			row = append(row, trainValue(role, column.key))
		}
		rows = append(rows, row)
	}
	return output.Table(out, headers, rows, 1, len(headers)-1)
}

func renderTrainPage(out io.Writer, page platform.Page, heading string, columns []recordColumn, empty string) error {
	if heading != "" {
		fmt.Fprintln(out, heading)
	}
	format := func(item platform.Record, key string) string {
		if key == "status" && empty == "暂无执行记录" {
			if label := trainStatus[item.Text(key)]; label != "" {
				return label
			}
		}
		if key == "runningTime" && empty == "暂无执行实例" {
			if value, err := strconv.ParseFloat(fieldText(item["createTime"]), 64); err == nil {
				mins := max(0, (time.Now().UnixMilli()-int64(value))/60000)
				return trainValue(platform.Record{"runningTime": json.RawMessage(strconv.FormatInt(mins, 10))}, key)
			}
		}
		return trainValue(item, key)
	}
	if err := renderRecordTable(out, columns, page.Items, format); err != nil {
		return err
	}
	if len(page.Items) == 0 {
		fmt.Fprintln(out, empty)
	}
	_, err := fmt.Fprintf(out, "第 %d 页 · 每页 %d 条 · 共 %d 条\n", page.PageIndex, page.PageSize, page.Count)
	return err
}

func renderTrainHistoryDetail(out io.Writer, item platform.Record, taskID, jobID, format string) error {
	if format == "json" {
		return output.JSON(out, item)
	}
	if item.Text("jobType") != "dps-train" {
		return renderTrainPage(out, platform.Page{Count: 1, PageIndex: 1, PageSize: 1, Items: []platform.Record{item}},
			"任务 ID："+taskID, trainHistoryColumns, "")
	}
	var roles []platform.Record
	if json.Unmarshal(item["roleJobInfo"], &roles) != nil || roles == nil {
		return fmt.Errorf("分布式执行记录缺少有效的 roleJobInfo 数组")
	}
	for _, role := range roles {
		if role == nil {
			return fmt.Errorf("分布式执行记录的 roleJobInfo 包含无效记录")
		}
	}
	fmt.Fprintf(out, "任务 ID：%s\n作业 ID：%s\n任务类型：分布式训练\n", taskID, jobID)
	if err := renderRecordTable(out, trainRoles, roles, trainValue); err != nil {
		return err
	}
	if len(roles) == 0 {
		_, err := fmt.Fprintln(out, "暂无角色信息")
		return err
	}
	return nil
}
