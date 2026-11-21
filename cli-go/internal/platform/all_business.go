package platform

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
)

func (a *API) RequireAllBusiness(ctx context.Context) error {
	if !a.credentials.HasAdminFlags() {
		if err := a.refreshAdminFlags(ctx); err != nil {
			return err
		}
	}
	if !a.credentials.CanQueryAllBusiness() {
		return errors.New("当前账号不具备超级管理员或超级管理员只读权限，无法使用 --all-business")
	}
	return nil
}

func (a *API) refreshAdminFlags(ctx context.Context) error {
	payload, err := a.JSON(ctx, http.MethodGet, "/ai/user/info", nil, nil)
	if err != nil {
		return err
	}
	result, err := Result(payload, "查询当前账号权限", false)
	if err != nil {
		return err
	}
	var superAdmin, aiSupporter *bool
	if json.Unmarshal(result["isSuperAdmin"], &superAdmin) != nil || superAdmin == nil ||
		json.Unmarshal(result["isAISupporter"], &aiSupporter) != nil || aiSupporter == nil {
		return errors.New("管理台未返回有效的超级管理员权限标志，请重新登录或联系管理员")
	}
	if err := a.session.Paths.UpdateAdminFlags(a.credentials, *superAdmin, *aiSupporter); err != nil && a.session.Stderr != nil {
		fmt.Fprintln(a.session.Stderr, "[警告] 无法保存当前账号权限，下次跨租户查询将重新核对")
	}
	a.credentials.IsSuperAdmin, a.credentials.IsAISupporter = superAdmin, aiSupporter
	return nil
}
