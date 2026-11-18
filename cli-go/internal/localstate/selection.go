package localstate

import (
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"time"
)

func (p Paths) UseEnvironment(name string) (Profile, error) {
	unlock, err := p.LockState()
	if err != nil {
		return Profile{}, err
	}
	defer unlock()
	cfg, err := LoadConfig(p)
	if err != nil {
		return Profile{}, err
	}
	for _, profile := range cfg.Profiles {
		if profile.Name != name {
			continue
		}
		var document map[string]json.RawMessage
		if err := readJSON(p.Config(), &document); err != nil {
			return Profile{}, err
		}
		document["current"], _ = json.Marshal(name)
		return profile, writeState(p.Config(), document)
	}
	return Profile{}, fmt.Errorf("环境 %q 不存在", name)
}

func (p Paths) BrowserProfile(profile Profile) string {
	key := sha256.Sum256([]byte(profile.Name + "\x00" + profile.Origin()))
	return filepath.Join(p.Dir, "edge", fmt.Sprintf("%x", key))
}

func (p Paths) Logout(profile Profile, all, forget bool) error {
	unlockLogin, err := p.LockLogin()
	if err != nil {
		return err
	}
	defer unlockLogin()
	unlock, err := p.LockState()
	if err != nil {
		return err
	}
	defer unlock()
	file := credentialFile{}
	if err := readExisting(p.Credentials(), &file); err != nil {
		return err
	}
	if all {
		if err := os.Remove(p.Credentials()); err != nil && !errors.Is(err, os.ErrNotExist) {
			return err
		}
	} else if _, exists := file.Profiles[profile.Name]; exists {
		delete(file.Profiles, profile.Name)
		if err := writeState(p.Credentials(), file); err != nil {
			return err
		}
	}
	if !forget {
		return nil
	}
	if all {
		return os.RemoveAll(filepath.Join(p.Dir, "edge"))
	}
	return os.RemoveAll(p.BrowserProfile(profile))
}

func (p Paths) SelectBusiness(profile Profile, creds Credentials, department, tenant, team string) (BusinessEntry, error) {
	unlock, err := p.LockState()
	if err != nil {
		return BusinessEntry{}, err
	}
	defer unlock()
	cfg, err := LoadConfig(p)
	if err != nil {
		return BusinessEntry{}, err
	}
	if cfg.Current != profile.Name || cfg.Profile().Origin() != profile.Origin() {
		return BusinessEntry{}, errors.New("选择期间当前环境已变化，请重新选择")
	}
	latest, err := p.LoadCredentials(profile, time.Now())
	if err != nil {
		return BusinessEntry{}, err
	}
	if latest.StateID != creds.StateID || latest.Username != creds.Username {
		return BusinessEntry{}, errors.New("选择期间登录账号或业务目录已变化，请重新选择")
	}
	var file businessFile
	if err := readJSON(p.Business(), &file); err != nil {
		return BusinessEntry{}, err
	}
	entry, err := file.entry(latest, false)
	if err != nil {
		return BusinessEntry{}, err
	}
	selection, err := chooseBusiness(entry.Catalog, department, tenant, team)
	if err != nil {
		return BusinessEntry{}, err
	}
	entry.Selected = selection
	file.Profiles[profile.Name] = entry
	return entry, writeState(p.Business(), file)
}

func chooseBusiness(catalog []Department, department, tenant, team string) (Selection, error) {
	var matches []Selection
	for _, dept := range catalog {
		if department != "" && dept.ID != department {
			continue
		}
		for _, item := range dept.Tenants {
			if item.ID != tenant {
				continue
			}
			if team == "" && validHeader(item.ID) {
				matches = append(matches, Selection{DepartmentID: dept.ID, TenantID: item.ID, BusinessID: item.ID})
				continue
			}
			for _, candidate := range item.Teams {
				if (candidate.ID == team || candidate.Key == team) && candidate.Status == "available" && validHeader(candidate.BusinessID) {
					matches = append(matches, Selection{dept.ID, item.ID, candidate.ID, candidate.BusinessID})
				}
			}
		}
	}
	if len(matches) != 1 {
		return Selection{}, errors.New("业务不可选或存在歧义，请用 ml business list 核对部门、租户和团队 ID")
	}
	return matches[0], nil
}
