package localstate

func (c Credentials) HasAdminFlags() bool {
	return c.IsSuperAdmin != nil && c.IsAISupporter != nil
}

func (c Credentials) CanQueryAllBusiness() bool {
	return c.IsSuperAdmin != nil && *c.IsSuperAdmin || c.IsAISupporter != nil && *c.IsAISupporter
}

func (c Credentials) AdminRoleLabel() string {
	switch {
	case c.IsSuperAdmin != nil && *c.IsSuperAdmin:
		return "超级管理员"
	case c.IsAISupporter != nil && *c.IsAISupporter:
		return "超级管理员（只读）"
	case c.HasAdminFlags():
		return "普通用户"
	default:
		return "未获取"
	}
}
