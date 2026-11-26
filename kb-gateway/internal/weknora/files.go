package weknora

import (
	"context"
	"net/http"
	"net/url"
	"strconv"
)

type knowledgeFile struct {
	ID        string `json:"id"`
	LibraryID string `json:"knowledge_base_id"`
	Name      string `json:"file_name"`
	Folder    string `json:"folder_path"`
	Size      *int64 `json:"file_size"`
	Path      string `json:"file_path"`
	Updated   string `json:"updated_at"`
	Status    string `json:"parse_status"`
}

func (f knowledgeFile) available(kbID string) bool {
	return f.LibraryID == kbID && len(f.ID) <= 36 && identifier.MatchString(f.ID) &&
		f.Name != "" && f.Path != "" && f.Status != "deleting"
}

func (c *Client) fileLibrary(ctx context.Context, env, user, name string, grants FileGrants) (library, obj, error) {
	if len(grants) == 0 {
		return library{}, nil, Failure{403, "FILE_ACCESS_DENIED"}
	}
	libraries, err := c.libraries(ctx)
	if err != nil {
		return library{}, nil, err
	}
	var visible []library
	for _, k := range libraries {
		if c.Visibility.allows(k.ID, env, user) && grants.allows(k.ID, env, user) {
			visible = append(visible, k)
		}
	}
	return matchLibrary(visible, name)
}

func (c *Client) listFiles(ctx context.Context, env, user string, q url.Values) (obj, error) {
	page, err := number(q, "page", 1, 1<<26)
	if err != nil {
		return nil, err
	}
	size, err := number(q, "page_size", 20, 50)
	if err != nil {
		return nil, err
	}
	k, result, err := c.fileLibrary(ctx, env, user, q.Get("kb"), c.FileList)
	if err != nil {
		return result, err
	}
	var response struct {
		Data  []knowledgeFile
		Total *int
	}
	params := url.Values{"page": {strconv.Itoa(page)}, "page_size": {strconv.Itoa(size)},
		"sort_by": {"created_at"}, "sort_order": {"asc"}}
	err = c.get(ctx, "knowledge-bases/"+url.PathEscape(k.ID)+"/knowledge", params, &response)
	if err != nil {
		return nil, err
	}
	if response.Total == nil || *response.Total < 0 {
		return nil, upstream
	}
	start := int64(page-1) * int64(size)
	total := int64(*response.Total)
	if int64(len(response.Data)) != max(0, min(int64(size), total-start)) {
		return nil, upstream
	}
	items := []obj{}
	for _, file := range response.Data {
		if file.available(k.ID) {
			items = append(items, obj{"id": file.ID, "file_name": file.Name, "folder_path": file.Folder,
				"file_size": file.Size, "updated_at": stamp(file.Updated)})
		}
	}
	return obj{"kb_id": k.ID, "kb_name": k.Name, "page": page, "page_size": size,
		"has_more": start+int64(size) < total, "items": items}, nil
}

func (c *Client) OpenFile(ctx context.Context, env, user string, q url.Values) (*http.Response, string, obj, error) {
	id, name := q.Get("id"), q.Get("kb")
	if len(id) > 36 || !identifier.MatchString(id) || name == "" {
		return nil, "", nil, invalid
	}
	k, result, err := c.fileLibrary(ctx, env, user, name, c.FileDownload)
	if err != nil {
		return nil, "", result, err
	}
	result = obj{"kb_id": k.ID}
	var response struct{ Data knowledgeFile }
	path := "knowledge/" + url.PathEscape(id)
	if err := c.get(ctx, path, nil, &response); err != nil {
		return nil, "", result, err
	}
	file := response.Data
	if file.ID != id || !file.available(k.ID) {
		return nil, "", result, Failure{404, "FILE_NOT_FOUND"}
	}
	if file.Size != nil && *file.Size > c.MaxFileBytes {
		return nil, "", result, Failure{413, "FILE_TOO_LARGE"}
	}
	resp, err := c.open(ctx, path+"/download", nil)
	if err != nil {
		return nil, "", result, err
	}
	if resp.ContentLength < 0 && file.Size != nil {
		resp.ContentLength = *file.Size
	}
	if resp.ContentLength < 0 || (file.Size != nil && resp.ContentLength != *file.Size) {
		resp.Body.Close()
		return nil, "", result, upstream
	}
	if resp.ContentLength > c.MaxFileBytes {
		resp.Body.Close()
		return nil, "", result, Failure{413, "FILE_TOO_LARGE"}
	}
	return resp, file.Name, result, nil
}
