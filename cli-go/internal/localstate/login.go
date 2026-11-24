package localstate

import (
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"time"
)

func (p Paths) LockLogin() (func(), error) {
	return p.lock("edge-login.lock")
}

func (p Paths) LockState() (func(), error) {
	return p.lockStateWithin(DefaultLockWait)
}

func (p Paths) lockStateWithin(wait time.Duration) (func(), error) {
	return p.lockWithin("state.lock", wait)
}

func (p Paths) LockPing() (func(), error) { return p.lock("ping-go.lock") }

func (p Paths) LockPingWithin(wait time.Duration) (func(), error) {
	return p.lockWithin("ping-go.lock", wait)
}

func (p Paths) SaveLogin(creds Credentials, catalog []Department, browserBusinessID, scopeTenantID string) (string, error) {
	return p.saveLogin(creds, catalog, browserBusinessID, scopeTenantID, false)
}

func (p Paths) SaveBusinessRefresh(creds Credentials, catalog []Department, browserBusinessID string) (string, error) {
	return p.saveLogin(creds, catalog, browserBusinessID, "", true)
}

func (p Paths) saveLogin(creds Credentials, catalog []Department, browserBusinessID, scopeTenantID string, preserveSelection bool) (string, error) {
	if err := p.ValidateSession(); err != nil {
		return "", err
	}
	unlock, err := p.LockState()
	if err != nil {
		return "", err
	}
	defer unlock()
	credentialData := credentialFile{}
	if err := readExisting(p.Credentials(), &credentialData); err != nil {
		return "", err
	}
	businessData := businessFile{Version: 2}
	if err := readExisting(p.Business(), &businessData); err != nil {
		return "", err
	}
	if businessData.Version != 2 {
		return "", errors.New("business.json 版本不兼容")
	}
	if credentialData.Profiles == nil {
		credentialData.Profiles = make(map[string]Credentials)
	}
	if businessData.Profiles == nil {
		businessData.Profiles = make(map[string]BusinessEntry)
	}
	creds.StateID = NewID()
	browserBusinessID = strings.TrimSpace(browserBusinessID)
	browserSelection := selectionFromBrowser(catalog, browserBusinessID, false)
	loginSelection := browserSelection
	if !preserveSelection && browserBusinessID == "" {
		loginSelection = selectionFromBrowser(catalog, scopeTenantID, true)
	}
	isolated := p.IsSessionIsolated()
	entry := BusinessEntry{Username: creds.Username, StateID: creds.StateID, Catalog: catalog, Selected: browserSelection}
	if !isolated {
		entry.Selected = loginSelection
	}
	previous := businessData.Profiles[creds.Profile]
	oldCredentials := credentialData.Profiles[creds.Profile]
	if (preserveSelection || isolated) &&
		oldCredentials.Origin == creds.Origin && oldCredentials.StateID == previous.StateID &&
		previous.Username == creds.Username && matchesSelection(catalog, previous.Selected) {
		entry.Selected = previous.Selected
	}
	businessData.Profiles[creds.Profile] = entry
	credentialData.Profiles[creds.Profile] = creds
	// Readers use the same state ID in both files and reject a partially written login.
	if err := writeState(p.Business(), businessData); err != nil {
		return "", err
	}
	if err := writeState(p.Credentials(), credentialData); err != nil {
		return "", err
	}
	if !isolated {
		return entry.Selected.BusinessID, nil
	}
	var sessionBusinessID string
	err = p.UpdateSessionState(func(state *SessionState) error {
		if state.Selections == nil {
			state.Selections = make(map[string]SessionSelection)
		}
		if existing, ok := state.Selections[creds.Profile]; ok && preserveSelection &&
			existing.Username == creds.Username && validHeader(existing.BusinessID) &&
			matchesSelection(catalog, existing.toSelection()) {
			sessionBusinessID = existing.BusinessID
			return nil
		}
		if loginSelection.BusinessID != "" {
			state.Selections[creds.Profile] = sessionSelectionFrom(creds.Username, loginSelection)
			sessionBusinessID = loginSelection.BusinessID
			return nil
		}
		delete(state.Selections, creds.Profile)
		sessionBusinessID = ""
		return nil
	})
	if err != nil {
		return "", err
	}
	return sessionBusinessID, nil
}

func (p Paths) UpdateAdminFlags(expected Credentials, superAdmin, aiSupporter bool) error {
	unlock, err := p.LockState()
	if err != nil {
		return err
	}
	defer unlock()
	var file credentialFile
	if err := readJSON(p.Credentials(), &file); err != nil {
		return err
	}
	current := file.Profiles[expected.Profile]
	if current.Profile != expected.Profile || current.Origin != expected.Origin ||
		current.StateID != expected.StateID || current.Username != expected.Username {
		return errors.New("登录会话已变更，无法保存管理角色")
	}
	current.IsSuperAdmin, current.IsAISupporter = &superAdmin, &aiSupporter
	file.Profiles[expected.Profile] = current
	return writeState(p.Credentials(), file)
}

func selectionFromBrowser(catalog []Department, id string, tenantOnly bool) Selection {
	if !validHeader(id) {
		return Selection{}
	}
	var matches []Selection
	for _, department := range catalog {
		for _, tenant := range department.Tenants {
			if tenant.ID == id {
				matches = append(matches, Selection{DepartmentID: department.ID, TenantID: tenant.ID, BusinessID: tenant.ID})
			}
			if tenantOnly {
				continue
			}
			for _, team := range tenant.Teams {
				if (id == team.ID || id == team.Key || id == team.BusinessID) &&
					team.Status == "available" && validHeader(team.BusinessID) {
					matches = append(matches, Selection{department.ID, tenant.ID, team.ID, team.BusinessID})
				}
			}
		}
	}
	if len(matches) == 1 {
		return matches[0]
	}
	return Selection{}
}

func readExisting(path string, target any) error {
	contents, err := os.ReadFile(path)
	if errors.Is(err, os.ErrNotExist) {
		return nil
	}
	if err != nil || json.Unmarshal(contents, target) != nil {
		return errors.New("无法读取现有预览状态：" + filepath.Base(path))
	}
	return nil
}

func writeState(path string, value any) error {
	data, err := json.Marshal(value)
	if err != nil {
		return errors.New("无法生成预览状态：" + filepath.Base(path))
	}
	if err := WritePrivate(path, data); err != nil {
		return errors.New("无法写入预览状态：" + filepath.Base(path))
	}
	return nil
}
