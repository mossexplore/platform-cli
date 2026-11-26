package output

import "testing"

func TestAgentListPagination(t *testing.T) {
	for _, mode := range []string{"paged", "fixedFirstPage", "unpaged", "limited"} {
		t.Run(mode, func(t *testing.T) {
			result := AgentList([]string{}, map[string]string{"id": "资源 ID"}, mode, 1, 10, nil)
			want := mode == "paged" || mode == "fixedFirstPage"
			for _, key := range []string{"pageIndex", "pageSize"} {
				if _, ok := result[key]; ok != want {
					t.Fatalf("%s present=%t, want %t", key, ok, want)
				}
			}
		})
	}
}
