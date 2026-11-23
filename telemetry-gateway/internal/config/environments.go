package config

import (
	"errors"
	"regexp"
	"strings"
)

var environmentName = regexp.MustCompile(`^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}$`)

// EnvironmentSet allows every environment when its map is nil.
type EnvironmentSet map[string]struct{}

func NormalizeEnvironment(name string) string {
	if !environmentName.MatchString(name) {
		return ""
	}
	return strings.ToLower(name)
}

func ParseEnvironments(value string) (EnvironmentSet, error) {
	value = strings.TrimSpace(value)
	if value == "" || value == "*" {
		return nil, nil
	}
	set := make(EnvironmentSet)
	if value == "-" {
		return set, nil
	}
	for raw := range strings.SplitSeq(value, ",") {
		name := NormalizeEnvironment(strings.TrimSpace(raw))
		if name == "" {
			return nil, errors.New("expected comma-separated environment names, * or -")
		}
		set[name] = struct{}{}
	}
	return set, nil
}

func (set EnvironmentSet) Allows(name string) bool {
	_, found := set[name]
	return set == nil || found
}
