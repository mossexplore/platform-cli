package command

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/mossexplore/platform-cli/cli-go/internal/output"
	"github.com/mossexplore/platform-cli/cli-go/internal/platform"
	"github.com/spf13/cobra"
)

type catalogQuery struct {
	route                string
	command              string
	summary              string
	args                 int
	paged                bool
	allowAllBusiness     bool
	appendBusinessColumn bool
	maxPage              int
	strings              []string
	nullable             []string
	defaults             map[string]string
	fixed                map[string]any
	assign               map[string]string
	wiseref              bool
	body                 func(map[string]any, *cobra.Command, []string, *platform.API) (any, error)
	selectData           func(platform.Record) (platform.Record, error)
	items                string
	total                string
	totalJSON            string
	optionalTotal        bool
	preserve             bool
	paginationFromServer bool
	optionalCode         bool
	columns              []recordColumn
	fields               []recordColumn
	empty                string
	value                func(platform.Record, string) string
}

func (q catalogQuery) build(options Options, load loadConfig) *cobra.Command {
	cmd := &cobra.Command{Use: q.command, Short: q.summary, Args: positional(q.args)}
	if q.wiseref {
		cmd.Annotations = map[string]string{"platform": "wiserec"}
	}
	outputFlag(cmd)
	if q.allowAllBusiness {
		addAllBusinessFlag(cmd)
	}
	if q.paged {
		pagination(cmd)
	}
	for _, flag := range append(append([]string{}, q.strings...), q.nullable...) {
		cmd.Flags().String(flag, q.defaults[flag], flag)
	}
	cmd.RunE = authorized(options, load, func(cmd *cobra.Command, args []string, api *platform.API, format string) error {
		page, size := 1, 10
		body := map[string]any{}
		for key, value := range q.fixed {
			body[key] = value
		}
		if q.paged {
			page, _ = cmd.Flags().GetInt("page")
			size, _ = cmd.Flags().GetInt("page-size")
			if page < 1 || size < 1 || q.maxPage > 0 && size > q.maxPage {
				return usageError{errors.New("page 或 page-size 超出有效范围")}
			}
			body["pageIndex"], body["pageSize"] = page, size
		}
		for flag, field := range q.assign {
			value, _ := cmd.Flags().GetString(flag)
			body[field] = value
		}
		for _, flag := range q.nullable {
			if !cmd.Flags().Changed(flag) {
				body[q.assign[flag]] = nil
			}
		}
		request := any(body)
		if q.body != nil {
			var err error
			request, err = q.body(body, cmd, args, api)
			if err != nil {
				return err
			}
		}
		payload, err := api.JSON(cmd.Context(), http.MethodPost, q.route, nil, request)
		if err != nil {
			return err
		}
		result, err := catalogResult(payload, q.summary, q.optionalCode)
		if err != nil {
			return err
		}
		if q.selectData != nil {
			result, err = q.selectData(result)
			if err != nil {
				return err
			}
		}
		return q.render(cmd.OutOrStdout(), result, payload, format, page, size, allBusinessRequested(cmd))
	})
	return cmd
}

func catalogResult(payload json.RawMessage, label string, optional bool) (platform.Record, error) {
	if optional {
		var envelope platform.Record
		if json.Unmarshal(payload, &envelope) == nil {
			if result := envelope.Object("result"); result != nil && len(result["code"]) == 0 {
				return result, nil
			}
		}
	}
	return platform.Result(payload, label, false)
}

func (q catalogQuery) render(out io.Writer, record platform.Record, raw json.RawMessage, format string, page, size int, allBusiness bool) error {
	value := q.value
	if value == nil {
		value = catalogValue
	}
	if q.items == "" {
		if format == "json" {
			if q.preserve {
				return output.JSON(out, raw)
			}
			return output.JSON(out, record)
		}
		if len(q.fields) == 0 {
			data, err := json.Marshal(record)
			if err != nil {
				return err
			}
			return output.ResultTable(out, data)
		}
		fields := output.Fields{}
		for _, field := range q.fields {
			fields = append(fields, output.Field{Key: field.title, Value: value(record, field.key)})
		}
		return fields.Table(out)
	}
	var items []platform.Record
	if json.Unmarshal(record[q.items], &items) != nil || items == nil {
		return fmt.Errorf("响应缺少有效的 %s 数组", q.items)
	}
	for _, item := range items {
		if item == nil {
			return fmt.Errorf("%s 包含无效条目", q.items)
		}
	}
	total := (*int)(nil)
	if q.total != "" {
		if field := record[q.total]; len(field) > 0 {
			if json.Unmarshal(field, &total) != nil || total != nil && *total < 0 {
				return fmt.Errorf("响应缺少有效的 %s", q.total)
			}
		}
		if total == nil && !q.optionalTotal {
			return fmt.Errorf("响应缺少有效的 %s", q.total)
		}
	}
	if q.paginationFromServer {
		for key, target := range map[string]*int{"pageIndex": &page, "pageSize": &size} {
			if field, exists := record[key]; exists && (json.Unmarshal(field, target) != nil || *target < 1 || string(field) == "null") {
				return errors.New("响应分页信息无效")
			}
		}
	}
	if format == "json" {
		if q.preserve {
			return output.JSON(out, raw)
		}
		result := map[string]any{"items": items, "pageIndex": page, "pageSize": size}
		if total != nil {
			result[q.totalJSON] = *total
		}
		return output.JSON(out, result)
	}
	if err := renderRecordTable(out, allBusinessColumns(q.columns, allBusiness && q.appendBusinessColumn), items, value); err != nil {
		return err
	}
	if len(items) == 0 && q.empty != "" {
		fmt.Fprintln(out, q.empty)
	}
	if total != nil {
		_, err := fmt.Fprintf(out, "第 %d 页 · 每页 %d 条 · 共 %d 条\n", page, size, *total)
		return err
	}
	return nil
}

func withBusiness(body map[string]any, cmd *cobra.Command, _ []string, api *platform.API) (any, error) {
	setListBusiness(body, cmd, api.BusinessID())
	return body, nil
}

func dataRecord(record platform.Record) (platform.Record, error) {
	if data := record.Object("data"); data != nil {
		return data, nil
	}
	return nil, errors.New("响应缺少有效的 result.data")
}

func catalogValue(record platform.Record, field string) string {
	switch field {
	case "createTime", "updateTime", "modifyTime", "useTime", "latestRunTime", "checkTime", "statusTime", "createDate", "updateDate", "startTime", "endTime", "lastModifyDate":
		raw := record[field]
		if number, err := strconv.ParseFloat(string(raw), 64); err == nil && math.Abs(number) < 100_000_000_000 {
			seconds, fraction := math.Modf(number)
			return time.Unix(int64(seconds), int64(fraction*1e9)).In(beijing).Format("2006-01-02 15:04:05")
		}
		return dateText(raw)
	case "latestFlag":
		return yesNo(record[field])
	default:
		return trainValue(record, field)
	}
}

func defaultFields(blank, null, arrays string) map[string]any {
	data := map[string]any{}
	for _, field := range strings.Fields(blank) {
		data[field] = ""
	}
	for _, field := range strings.Fields(null) {
		data[field] = nil
	}
	for _, field := range strings.Fields(arrays) {
		data[field] = []string{}
	}
	return data
}

func readableBytes(value string) string {
	size, err := strconv.ParseFloat(value, 64)
	if err != nil || size < 0 || math.IsNaN(size) || math.IsInf(size, 0) {
		return value
	}
	if size < 1024 {
		return value + " B"
	}
	for _, unit := range []string{"KB", "MB", "GB", "TB", "PB", "EB"} {
		size /= 1024
		if size < 1024 || unit == "EB" {
			return fmt.Sprintf("%.2f %s", size, unit)
		}
	}
	return value
}
