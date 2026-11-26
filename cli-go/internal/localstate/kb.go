package localstate

import (
	"encoding/json"
	"errors"
	"fmt"
	"net/url"
	"os"
	"path/filepath"
)

type KnowledgeBase struct {
	Enable  bool   `json:"enable"`
	URL     string `json:"url"`
	Default string `json:"default_kb"`
	Timeout int    `json:"timeout_seconds"`
	Verify  *bool  `json:"verify_ssl"`
}

func (k KnowledgeBase) validate(access string) error {
	if !k.Enable {
		return nil
	}
	for _, s := range []string{k.URL, access} {
		u, e := url.Parse(s)
		if e != nil || u.Scheme != "https" || u.Hostname() == "" || u.User != nil || u.RawQuery != "" || u.Fragment != "" {
			return errors.New("知识库和权限服务均须配置可信 HTTPS 地址")
		}
	}
	if k.Verify != nil && !*k.Verify || k.Timeout < 0 || k.Timeout > 120 {
		return errors.New("知识库配置无效，请启用证书校验并检查超时")
	}
	return nil
}
func (p Paths) KBSettings() (KnowledgeBase, error) {
	if p.packaged == nil {
		return KnowledgeBase{}, errors.New("缺少打包配置")
	}
	k := p.packaged.Knowledge
	path := filepath.Join(p.Dir, "kb.json")
	data, e := os.ReadFile(path)
	if errors.Is(e, os.ErrNotExist) {
		return k, nil
	}
	if e != nil {
		return k, e
	}
	var o struct {
		Enable  *bool   `json:"enable"`
		Default *string `json:"default_kb"`
	}
	if e = json.Unmarshal(data, &o); e != nil {
		return k, fmt.Errorf("知识库配置 %s 无效: %w", path, e)
	}
	if o.Enable != nil && !*o.Enable {
		k.Enable = false
	}
	if o.Default != nil {
		k.Default = *o.Default
	}
	return k, nil
}
