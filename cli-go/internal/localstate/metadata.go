package localstate

import (
	"crypto/rand"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strings"
)

func NewID() string {
	value := [16]byte{}
	// The Go runtime terminates if its OS random source fails.
	_, _ = rand.Read(value[:])
	value[6] = value[6]&0x0f | 0x40
	value[8] = value[8]&0x3f | 0x80
	return fmt.Sprintf("%x-%x-%x-%x-%x", value[:4], value[4:6], value[6:8], value[8:10], value[10:])
}

var identifier = regexp.MustCompile(`(?i)^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$`)

func (p Paths) InstallationID() string {
	name := filepath.Join(p.Dir, "installation-id")
	file, err := os.OpenFile(name, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
	if err == nil {
		value := NewID()
		_, writeErr := file.WriteString(value)
		closeErr := file.Close()
		if writeErr != nil || closeErr != nil {
			_ = os.Remove(name)
			return ""
		}
		return value
	}
	if errors.Is(err, os.ErrExist) {
		raw, err := os.ReadFile(name)
		value := strings.TrimSpace(string(raw))
		if err == nil && identifier.MatchString(value) {
			return strings.ToLower(value)
		}
	}
	return ""
}

type Policy struct {
	Environment string   `json:"environment"`
	Origin      string   `json:"platform_origin"`
	Revision    *int     `json:"revision"`
	Deny        []string `json:"deny"`
}

func (p Paths) Policy(settings Access, profile Profile) *Policy {
	var policy Policy
	if readJSON(p.policyPath(settings, profile), &policy) != nil || !policy.valid(profile) {
		return nil
	}
	return &policy
}

func (p Paths) RememberPolicy(settings Access, profile Profile, data json.RawMessage) {
	var policy Policy
	if json.Unmarshal(data, &policy) == nil && policy.valid(profile) {
		_ = WritePrivate(p.policyPath(settings, profile), data)
	}
}

func (p Paths) policyPath(settings Access, profile Profile) string {
	values := []string{strings.TrimRight(settings.URL, "/"), profile.Name, profile.Origin()}
	identity, _ := json.Marshal(values)
	return filepath.Join(p.Dir, "command-policies", fmt.Sprintf("%x.json", sha256.Sum256(identity)))
}

func (p Policy) valid(profile Profile) bool {
	if p.Environment != profile.Name || p.Origin != profile.Origin() ||
		p.Revision == nil || *p.Revision < 0 || p.Deny == nil {
		return false
	}
	for _, rule := range p.Deny {
		if !strings.HasPrefix(rule, "ml ") {
			return false
		}
	}
	return validateDeny(p.Deny) == nil
}

func WritePrivate(path string, contents []byte) error {
	dir := filepath.Dir(path)
	if err := os.MkdirAll(dir, 0700); err != nil {
		return err
	}
	file, err := os.CreateTemp(dir, ".ml-go-*")
	if err != nil {
		return err
	}
	defer os.Remove(file.Name())
	_, writeErr := file.Write(contents)
	err = errors.Join(writeErr, file.Close())
	if err != nil {
		return err
	}
	return os.Rename(file.Name(), path)
}
