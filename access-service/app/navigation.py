"""Shared navigation groups and breadcrumb ownership."""

def item(key, label, url):
    return dict(key=key, label=label, url='/cli-permission/admin' + url)


GROUPS = [
    dict(label='访问控制', items_list=[
        item('applications', '权限审批', '/applications'),
        item('users', '人员授权', '?tab=users'),
        item('environments', '环境管理', '?tab=environments'),
        item('versions', '版本管理', '/versions')]),
    dict(label='监控与审计', items_list=[
        item('analytics', '数据看板', '/analytics'),
        item('calls', '调用日志', '/calls'),
        item('audit', '操作审计', '?tab=audit')]),
    dict(label='系统管理', super_only=True, items_list=[
        item('administrators', '管理员管理', '/administrators')]),
    dict(label='个人设置', owner_only=True, items_list=[
        item('notifications', '个人通知', '/notifications')]),
]
ROOTS = {entry['key']: group['label'] for group in GROUPS for entry in group['items_list']}
ROOTS['grants'] = '访问控制'
