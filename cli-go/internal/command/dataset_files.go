package command

import (
	"encoding/json"
	"errors"
	"fmt"
	"math"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"time"
	"unicode"

	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
	"github.com/mossexplore/platform-cli/cli-go/internal/output"
	"github.com/mossexplore/platform-cli/cli-go/internal/platform"
	"github.com/spf13/cobra"
)

const datasetPrefix = "/ai/backend/mtp/dataSet/"
const maxDatasetUpload = 2_000_000_000

var datasetNamePattern = regexp.MustCompile(`^[a-zA-Z0-9][a-zA-Z0-9_.-]*$`)

func newDatasetFiles(options Options, load loadConfig) *cobra.Command {
	group := &cobra.Command{Use: "files", Short: "管理数据集目录和文件"}
	list := &cobra.Command{Use: "list DATASET_ID", Short: "查看指定目录内容", Args: positional(1)}
	dir := list.Flags().String("dir", "/", "数据集内部目录")
	outputFlag(list)
	list.RunE = authorized(options, load, func(cmd *cobra.Command, args []string, api *platform.API, format string) error {
		directory, err := datasetDir(*dir)
		if err != nil {
			return err
		}
		payload, err := api.JSON(cmd.Context(), http.MethodPost, datasetPrefix+"file/queryList", nil, datasetBody(api, args[0], directory, ""))
		if err != nil {
			return err
		}
		result, err := platform.Result(payload, "查询数据集目录", false)
		if err != nil {
			return err
		}
		info := result.Object("fileInfos")
		var files []platform.Record
		var more *bool
		if info == nil || json.Unmarshal(info["files"], &files) != nil || files == nil || json.Unmarshal(info["hasMore"], &more) != nil || more == nil {
			return errors.New("目录响应缺少有效的 files 或 hasMore")
		}
		rows := make([][]string, 0, len(files))
		for _, item := range files {
			var kind *bool
			var name, path *string
			if json.Unmarshal(item["dir"], &kind) != nil || kind == nil || json.Unmarshal(item["name"], &name) != nil || name == nil ||
				json.Unmarshal(item["path"], &path) != nil || path == nil {
				return errors.New("目录条目缺少有效的 name、path 或 dir")
			}
			fullPath, err := datasetDir(strings.TrimRight(directory, "/") + "/" + strings.TrimLeft(*path, "/"))
			if err != nil {
				return err
			}
			label := "文件"
			if *kind {
				label = "文件夹"
			}
			rows = append(rows, []string{label, *name, catalogValue(item, "lastModifyDate"), trainValue(platform.Record{"fileSize": item["size"]}, "fileSize"), fullPath})
		}
		if *more {
			fmt.Fprintln(cmd.ErrOrStderr(), "[警告] 当前结果不完整，接口分页规则尚未提供")
		}
		if agentMode(cmd) {
			items := agentRows(files, nil, "name", "path", "size", "dir", "lastModifyDate")
			for i := range items {
				_ = items[i].Put("fullPath", rows[i][4])
			}
			mode := "unpaged"
			if *more {
				mode = "limited"
			}
			v := output.AgentList(items, mode, 0, 0, nil)
			v["currentDir"], v["hasMore"] = directory, *more
			return agentResult(cmd, v)
		}
		if format == "json" {
			return output.JSON(cmd.OutOrStdout(), map[string]any{"currentDir": directory, "response": payload})
		}
		fmt.Fprintln(cmd.OutOrStdout(), "当前位置："+directory)
		if err := output.Table(cmd.OutOrStdout(), []string{"类别", "文件名", "更新时间", "文件大小", "完整路径"}, rows); err != nil {
			return err
		}
		if len(rows) == 0 {
			_, err := fmt.Fprintln(cmd.OutOrStdout(), "当前目录为空")
			return err
		}
		return nil
	})
	upload := &cobra.Command{Use: "upload DATASET_ID LOCAL_FILE", Short: "向指定目录追加文件", Args: positional(2)}
	uploadDir := upload.Flags().String("dir", "/", "数据集内部目标目录")
	timeout := upload.Flags().Float64("timeout", 1800, "上传网络操作超时秒数")
	outputFlag(upload)
	upload.RunE = authorized(options, load, func(cmd *cobra.Command, args []string, api *platform.API, format string) error {
		if math.IsNaN(*timeout) || *timeout < 1 || *timeout > float64(math.MaxInt64/int64(time.Second)) {
			return usageError{errors.New("timeout 超出有效范围")}
		}
		file := args[1]
		if err := validateDatasetUpload(file); err != nil {
			return err
		}
		directory, err := datasetDir(*uploadDir)
		if err != nil {
			return err
		}
		payload, err := api.JSON(cmd.Context(), http.MethodPost, datasetPrefix+"queryDetail", nil,
			map[string]string{"dataSetId": args[0], "businessId": api.BusinessID(), "teamId": ""})
		if err != nil {
			return err
		}
		data, err := platform.Result(payload, "查询数据集详情", false)
		if err != nil {
			return err
		}
		target := data.Object("data").Text("dataSetName")
		if strings.TrimSpace(target) == "" {
			return errors.New("数据集详情缺少有效的 dataSetName")
		}
		targetDir := directory
		if targetDir == "/" {
			targetDir = ""
		}
		payload, err = api.Upload(cmd.Context(), datasetPrefix+"file/upload", url.Values{"target": {target}},
			datasetBody(api, args[0], targetDir, target), file, time.Duration(*timeout*float64(time.Second)), maxDatasetUpload)
		if err != nil {
			return err
		}
		if _, err := platform.Result(payload, "追加文件", false); err != nil {
			return err
		}
		if format == "json" {
			return output.JSON(cmd.OutOrStdout(), payload)
		}
		fmt.Fprintln(cmd.ErrOrStderr(), "[成功] 追加文件请求成功："+filepath.Base(file))
		fmt.Fprintln(cmd.OutOrStdout(), "当前位置："+directory)
		fmt.Fprintln(cmd.ErrOrStderr(), "[提示] 可使用 files list 查询目录确认文件处理结果")
		return nil
	})
	group.AddCommand(list, upload)
	return group
}

func datasetBody(api *platform.API, id, directory, target string) map[string]any {
	data := map[string]string{"dataSetId": id, "businessId": api.BusinessID(), "dir": directory}
	if target != "" {
		data["target"] = target
	}
	return map[string]any{"version": "1.0", "meta": map[string]string{"uuid": localstate.NewID()}, "data": data}
}

func datasetDir(input string) (string, error) {
	if input == "" || strings.Contains(input, "\\") || strings.IndexFunc(input, unicode.IsControl) >= 0 {
		return "", errors.New("目录不能为空或包含反斜杠、控制字符")
	}
	var normalized []string
	for _, item := range strings.Split(input, "/") {
		switch item {
		case "":
			continue
		case ".", "..":
			return "", errors.New("目录不能包含 . 或 .. 路径段")
		default:
			normalized = append(normalized, item)
		}
	}
	return "/" + strings.Join(normalized, "/"), nil
}

func validateDatasetUpload(name string) error {
	if !datasetNamePattern.MatchString(filepath.Base(name)) {
		return errors.New("文件名须以英文字母或数字开头，且仅包含英文字母、数字、_、-、.")
	}
	switch strings.ToLower(filepath.Ext(name)) {
	case ".txt", ".csv", ".zip", ".tar", ".gz", ".json":
	default:
		return errors.New("仅支持 .txt、.csv、.zip、.tar、.gz、.json 文件")
	}
	info, err := os.Stat(name)
	if err != nil || !info.Mode().IsRegular() || info.Size() > maxDatasetUpload {
		return errors.New("上传路径必须为存在的普通文件且不超过 2GB")
	}
	return nil
}
