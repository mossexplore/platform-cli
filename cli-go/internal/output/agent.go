package output

import "io"

// AgentWriter selects compact encoding for one command invocation.
type AgentWriter struct {
	io.Writer
}

func IsAgent(w io.Writer) bool {
	_, ok := w.(*AgentWriter)
	return ok
}

// AgentList describes row keys once, including when the result has no rows.
func AgentList[T any](items []T, fields map[string]string, mode string, page, size int, total *int) map[string]any {
	if items == nil {
		items = []T{}
	}
	result := map[string]any{"pagination": mode, "returnedCount": len(items), "items": items, "fields": fields}
	if (mode == "paged" || mode == "fixedFirstPage") && page > 0 && size > 0 {
		result["pageIndex"], result["pageSize"] = page, size
	}
	if total != nil {
		result["total"] = *total
	}
	return result
}
