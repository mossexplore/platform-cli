package weknora

import (
	"fmt"
	"regexp"
	"strings"
)

type Visibility struct {
	public, preview map[string]bool
	users           identityGrants
}

var identifier = regexp.MustCompile("^[A-Za-z0-9_-]+$")

type identityGrants map[[2]string]bool

func (g identityGrants) allows(env, user string) bool {
	return env != "" && user != "" && (g[[2]string{env, user}] || g[[2]string{env, "*"}] ||
		g[[2]string{"*", user}] || g[[2]string{"*", "*"}])
}

func validIdentitySelector(value string) bool {
	return value == "*" || value != "" && !strings.ContainsAny(value, "*?\r\n")
}

func ParseVisibility(public, preview, users string) (Visibility, error) {
	v := Visibility{map[string]bool{}, map[string]bool{}, make(identityGrants)}
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
			if !ok || !validIdentitySelector(env) || !validIdentitySelector(user) || strings.Contains(user, ":") {
				return Visibility{}, fmt.Errorf("invalid KB_PREVIEW_USERS entry")
			}
			v.users[[2]string{env, user}] = true
		}
	}
	return v, nil
}
func (v Visibility) allows(id, env, user string) bool {
	return v.public[id] || (v.preview[id] && v.users.allows(env, user))
}

type FileGrants map[string]identityGrants

func (g FileGrants) allows(id, env, user string) bool {
	return g[id].allows(env, user)
}

func ParseFileGrants(raw string) (FileGrants, error) {
	grants := make(FileGrants)
	if strings.TrimSpace(raw) == "" {
		return grants, nil
	}
	for _, entry := range strings.Split(raw, ",") {
		fields := strings.Split(strings.TrimSpace(entry), ":")
		if len(fields) != 3 || !validIdentitySelector(fields[0]) || !validIdentitySelector(fields[1]) ||
			!identifier.MatchString(fields[2]) {
			return nil, fmt.Errorf("文件授权项须使用 环境:账号:知识库ID")
		}
		env, user, id := fields[0], fields[1], fields[2]
		if grants[id] == nil {
			grants[id] = make(identityGrants)
		}
		grants[id][[2]string{env, user}] = true
	}
	return grants, nil
}
