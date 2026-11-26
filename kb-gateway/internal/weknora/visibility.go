package weknora

import (
	"fmt"
	"regexp"
	"strings"
)

type Visibility struct {
	public, preview map[string]bool
	users           map[[2]string]bool
}

var identifier = regexp.MustCompile("^[A-Za-z0-9_-]+$")

func ParseVisibility(public, preview, users string) (Visibility, error) {
	v := Visibility{map[string]bool{}, map[string]bool{}, map[[2]string]bool{}}
	for i, raw := range []string{public, preview} {
		if strings.TrimSpace(raw) == "" {
			continue
		}
		for _, entry := range strings.Split(raw, ",") {
			id := strings.TrimSpace(entry)
			if !identifier.MatchString(id) || v.public[id] || v.preview[id] {
				return Visibility{}, fmt.Errorf("invalid or overlapping knowledge base IDs")
			}
			if i == 0 {
				v.public[id] = true
			} else {
				v.preview[id] = true
			}
		}
	}
	if strings.TrimSpace(users) != "" {
		for _, entry := range strings.Split(users, ",") {
			env, user, ok := strings.Cut(strings.TrimSpace(entry), ":")
			if !ok || env == "" || user == "" || strings.Contains(user, ":") {
				return Visibility{}, fmt.Errorf("invalid KB_PREVIEW_USERS entry")
			}
			v.users[[2]string{env, user}] = true
		}
	}
	return v, nil
}
func (v Visibility) allows(id, env, user string) bool {
	return v.public[id] || (v.preview[id] && v.users[[2]string{env, user}])
}

type FileGrants map[[3]string]bool

func ParseFileGrants(raw string) (FileGrants, error) {
	grants := make(FileGrants)
	if strings.TrimSpace(raw) == "" {
		return grants, nil
	}
	for _, entry := range strings.Split(raw, ",") {
		fields := strings.Split(strings.TrimSpace(entry), ":")
		if len(fields) != 3 || fields[0] == "" || fields[1] == "" || !identifier.MatchString(fields[2]) ||
			strings.ContainsAny(fields[0]+fields[1], "*?\r\n") {
			return nil, fmt.Errorf("文件授权项须使用 环境:账号:知识库ID")
		}
		grants[[3]string{fields[0], fields[1], fields[2]}] = true
	}
	return grants, nil
}
