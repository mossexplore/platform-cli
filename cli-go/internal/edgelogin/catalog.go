package edgelogin

import (
	"encoding/json"
	"errors"
	"strings"

	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
)

func parseCatalog(raw string) ([]localstate.Department, error) {
	var source []struct {
		Department json.RawMessage `json:"settleTenantName"`
		Name       string          `json:"cn"`
		TenantID   json.RawMessage `json:"value"`
		Teams      []struct {
			ID         json.RawMessage `json:"teamId"`
			Key        json.RawMessage `json:"key"`
			Chinese    string          `json:"cn"`
			Name       json.RawMessage `json:"name"`
			Status     string          `json:"teamStatus"`
			BusinessID json.RawMessage `json:"businessId"`
		} `json:"teamList"`
	}
	if json.Unmarshal([]byte(raw), &source) != nil {
		return nil, errors.New("平台业务目录格式无效")
	}
	index := make(map[string]int)
	catalog := []localstate.Department{}
	for _, entry := range source {
		department := strings.TrimSpace(departmentName(entry.Department, entry.Name))
		tenantID := scalar(entry.TenantID)
		if department == "" || tenantID == "" {
			continue
		}
		if _, exists := index[department]; !exists {
			index[department] = len(catalog)
			catalog = append(catalog, localstate.Department{ID: department, Name: department})
		}
		tenant := localstate.Tenant{ID: tenantID, Name: entry.Name}
		for _, team := range entry.Teams {
			if id := scalar(team.ID); id != "" {
				tenant.Teams = append(tenant.Teams, localstate.Team{
					ID: id, Key: scalar(team.Key), Name: departmentName(team.Name, team.Chinese), Status: strings.TrimSpace(team.Status), BusinessID: scalar(team.BusinessID),
				})
			}
		}
		dept := &catalog[index[department]]
		dept.Tenants = append(dept.Tenants, tenant)
	}
	if len(catalog) == 0 {
		return nil, errors.New("平台业务目录没有可识别的租户")
	}
	return catalog, nil
}

func departmentName(raw json.RawMessage, fallback string) string {
	var text string
	if json.Unmarshal(raw, &text) == nil && text != "" {
		if !json.Valid([]byte(text)) {
			return text
		}
		raw = json.RawMessage(text)
	}
	var names struct {
		Chinese string `json:"cn"`
		English string `json:"en"`
	}
	if json.Unmarshal(raw, &names) == nil {
		if names.Chinese != "" {
			return names.Chinese
		}
		if names.English != "" {
			return names.English
		}
	}
	return fallback
}

func scalar(value json.RawMessage) string {
	var text string
	if json.Unmarshal(value, &text) == nil {
		return strings.TrimSpace(text)
	}
	var number json.Number
	if json.Unmarshal(value, &number) == nil {
		return number.String()
	}
	return ""
}
