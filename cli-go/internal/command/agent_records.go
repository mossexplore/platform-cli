package command

import (
	"encoding/json"
	"errors"
	"strings"
	"time"

	"github.com/mossexplore/platform-cli/cli-go/internal/platform"
)

func agentRecord(record platform.Record, keys ...string) platform.Record {
	result := platform.Record{}
	for _, key := range keys {
		raw := record[key]
		if len(raw) == 0 || string(raw) == "null" || string(raw) == `""` {
			continue
		}
		switch key {
		case "createTime", "updateTime", "modifyTime", "useTime", "latestRunTime", "checkTime", "statusTime", "createDate", "updateDate", "startTime", "endTime", "lastModifyDate":
			_ = result.Put(key, catalogValue(record, key))
		case "accessTime", "create_time", "update_time", "updated_at", "last_activity", "lastTimestamp":
			_ = result.Put(key, dateText(raw))
		case "latestCycleTime":
			// Some quality sources identify an hourly partition by YYYYMMDDHH.
			if _, err := time.Parse("2006010215", fieldText(raw)); err == nil {
				result[key] = raw
			} else {
				_ = result.Put(key, dateText(raw))
			}
		default:
			result[key] = raw
		}
	}
	return result
}

func agentFields(columns []recordColumn, extra map[string]string) map[string]string {
	fields := make(map[string]string, len(columns)+len(extra))
	for _, col := range columns {
		label := col.title
		switch col.key {
		case "fileSize", "pkgSize":
			label += "（字节）"
		case "runningTime", "queueTime":
			label += "（分钟）"
		case "waitTime":
			label += "（秒）"
		}
		fields[col.key] = label
	}
	for key, label := range extra {
		fields[key] = label
	}
	return fields
}

func columnKeys(columns []recordColumn, extra ...string) []string {
	keys := make([]string, 0, len(columns)+len(extra))
	for _, col := range columns {
		keys = append(keys, col.key)
	}
	return append(keys, extra...)
}

func agentRows(records []platform.Record, columns []recordColumn, extra ...string) []platform.Record {
	keys := columnKeys(columns, extra...)
	rows := make([]platform.Record, 0, len(records))
	for _, record := range records {
		rows = append(rows, agentRecord(record, keys...))
	}
	return rows
}

func agentHistory(record platform.Record, projected platform.Record) error {
	if raw := record["jobType"]; len(raw) > 0 {
		projected["jobType"] = raw
	}
	if record.Text("jobType") != "dps-train" {
		return projected.Put("plogReady", platform.HasPlog(record))
	}
	roles := []platform.Record{}
	if raw := record["roleJobInfo"]; len(raw) > 0 && string(raw) != "null" {
		if err := json.Unmarshal(raw, &roles); err != nil {
			return err
		}
	}
	rows := agentRows(roles, trainRoles)
	for i, role := range roles {
		if role == nil {
			return errors.New("roleJobInfo 包含无效记录")
		}
		_ = rows[i].Put("plogReady", platform.HasPlog(role))
	}
	return projected.Put("roleJobInfo", rows)
}

func agentCatalogProjection(q catalogQuery, records []platform.Record, all bool) ([]platform.Record, map[string]string) {
	extra := map[string]string{}
	if strings.HasSuffix(q.route, "rtcContainer/queryDetail") {
		extra = map[string]string{
			"imageName": "镜像名称", "imageVersion": "镜像版本",
			"wiseEyeName": "组件名称", "wiseEyeVersion": "组件版本",
			"cpuLimit": "CPU 上限", "memoryLimit": "内存上限",
			"gpuLimit": "GPU 上限", "npuLimit": "NPU 上限",
		}
	}
	if all {
		extra["businessId"] = "业务 ID"
	}
	keys := make([]string, 0, len(extra))
	for key := range extra {
		keys = append(keys, key)
	}
	rows := agentRows(records, q.columns, keys...)
	fields := agentFields(q.columns, extra)
	if q.route == datasetPrefix+"queryList" {
		fields["_truncated"] = "截断字段的原始长度"
		fields["_truncated.description"] = "描述截断前的字符数"
		for i, row := range rows {
			runes := []rune(records[i].Text("description"))
			if len(runes) > 256 {
				_ = row.Put("description", string(runes[:256]))
				_ = row.Put("_truncated", map[string]int{"description": len(runes)})
			}
		}
	}
	return rows, fields
}
