package platform

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"
)

type KBTicket struct {
	AK                                 string
	ID                                 string `json:"ticket_id"`
	Username, Environment, Action, Sig string
	Exp                                int64
}

var ErrKBRateLimited = errors.New("知识库网关请求过于频繁，HTTP 429")

func (s Session) ReadKB(ctx context.Context, command, path, audit string, q url.Values) (json.RawMessage, error) {
	var data json.RawMessage
	err := s.withKBResponse(ctx, command, path, audit, q, func(api *API, resp *http.Response) error {
		body, err := kbJSON(resp)
		if err != nil {
			return err
		}
		data = body
		return api.CheckTarget()
	})
	return data, err
}

func (s Session) DownloadKBFile(ctx context.Context, audit string, q url.Values, destination string) (string, int64, error) {
	var path string
	var size int64
	err := s.withKBResponse(ctx, "kb file download", "file", audit, q, func(api *API, resp *http.Response) error {
		disposition := resp.Header.Get("Content-Disposition")
		if resp.Header.Get("Content-Type") != "application/octet-stream" || resp.ContentLength < 0 || disposition == "" {
			return errors.New("知识库未返回有效的文件下载响应")
		}
		if destination == "" {
			destination = SafeDownloadName(disposition, q.Get("id")+".bin")
		}
		var err error
		path, size, err = saveDownload(destination, resp, nil, api.LockTarget)
		return err
	})
	return path, size, err
}

func (s Session) withKBResponse(ctx context.Context, command, path, audit string, q url.Values, use func(*API, *http.Response) error) error {
	action := strings.ReplaceAll(command, " ", "_")
	cfg, e := s.Paths.KBSettings()
	if e != nil {
		return e
	}
	if !cfg.Enable {
		return errors.New("知识库未启用")
	}
	api, e := s.Authorize(ctx, command, audit)
	if e != nil {
		return e
	}
	defer api.Close()
	t := api.metadata.ticket
	if t == nil || t.Action != action || t.Username != api.Username() || t.Environment != api.profile.Name || t.ID == "" || t.Sig == "" {
		return errors.New("权限服务未返回有效知识库票据，请检查签票配置和服务版本")
	}
	client, e := accessTransport(s.Config.Access)
	if e != nil {
		return e
	}
	defer client.CloseIdleConnections()
	client.Timeout = 15 * time.Second
	if cfg.Timeout > 0 {
		client.Timeout = time.Duration(cfg.Timeout) * time.Second
	}
	req, e := http.NewRequestWithContext(ctx, "GET", strings.TrimRight(cfg.URL, "/")+"/v1/kb/"+path, nil)
	if e != nil {
		return e
	}
	req.URL.RawQuery = q.Encode()
	for k, v := range map[string]string{"AK": t.AK, "Ticket-ID": t.ID, "User": t.Username, "Env": t.Environment, "Action": t.Action, "Exp": strconv.FormatInt(t.Exp, 10), "Signature": t.Sig} {
		req.Header.Set("X-KB-"+k, v)
	}
	req.Header.Set("businessid", api.BusinessID())
	req.Header.Set("X-Request-ID", api.metadata.id)
	if e := api.CheckTarget(); e != nil {
		return e
	}
	resp, e := client.Do(req)
	if e != nil {
		return errors.New("知识库 HTTPS 请求失败，请检查地址、证书和网络")
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 && resp.StatusCode < 400 {
		return fmt.Errorf("知识库网关返回 HTTP %d，已拒绝重定向，请核对网关地址和反代配置", resp.StatusCode)
	}
	if resp.StatusCode != http.StatusOK {
		_, err := kbJSON(resp)
		return err
	}
	return use(api, resp)
}

func kbJSON(resp *http.Response) (json.RawMessage, error) {
	if resp.StatusCode == http.StatusTooManyRequests {
		return nil, ErrKBRateLimited
	}
	body, e := io.ReadAll(io.LimitReader(resp.Body, 8<<20+1))
	if e != nil || len(body) > 8<<20 || !json.Valid(body) {
		return nil, errors.New("知识库响应无效或超限")
	}
	if resp.StatusCode != 200 {
		var f struct {
			Code       string
			Candidates []struct{ ID, Name string }
		}
		json.Unmarshal(body, &f)
		if f.Code == "AMBIGUOUS_KB_USE_ID" {
			var choices []string
			for _, candidate := range f.Candidates {
				choices = append(choices, fmt.Sprintf("%q (%s)", candidate.Name, candidate.ID))
			}
			return nil, fmt.Errorf("请通过 --kb 指定知识库 ID，可选知识库：%s", strings.Join(choices, "、"))
		}
		if f.Code == "UPSTREAM_RESPONSE_TOO_LARGE" {
			return nil, errors.New("上游响应超限，请调小 --page-size 或缩小查询范围")
		}
		return nil, fmt.Errorf("知识库请求失败 HTTP %d %s", resp.StatusCode, f.Code)
	}
	return body, nil
}
