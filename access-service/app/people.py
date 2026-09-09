"""人员与授权统一查询：按人员分页，包含尚未授权的账号。"""
from fastapi import HTTPException
from sqlalchemy import select, func, or_
from .models import User, Grant, Environment
from .pagination import PAGE_SIZE
from .admin_views import filter_status, grant_state, overview


def people_page(request, db, admin, session, page, q, status, grant_status, saved):
    if status not in ('', 'enabled', 'disabled') or grant_status not in ('', 'none', 'active', 'expired', 'expiring', 'disabled'):
        raise HTTPException(400, '无效状态筛选')
    query = select(User)
    if q:
        matching_env = select(Grant.user_id).join(Environment).where(Environment.name.contains(q, autoescape=True))
        query = query.where(or_(User.username.contains(q, autoescape=True),
            User.display_name.contains(q, autoescape=True), User.id.in_(matching_env)))
    if status:
        query = query.where(User.enabled.is_(status == 'enabled'))
    if grant_status == 'none':
        query = query.where(~User.id.in_(select(Grant.user_id)))
    elif grant_status:
        matches = filter_status(select(Grant.user_id).join(User).join(Environment), 'grants', grant_status)
        query = query.where(User.id.in_(matches))
    count = db.scalar(select(func.count()).select_from(query.subquery()))
    people = db.scalars(query.order_by(func.coalesce(User.updated_at, User.created_at).desc(), User.id.desc()).offset((page-1)*PAGE_SIZE).limit(PAGE_SIZE)).all()
    users = {user.id: user.username for user in people}
    grants = db.scalars(select(Grant).join(Environment).where(Grant.user_id.in_(users)).order_by(Environment.name)).all()
    env_objects = {env.id: env for env in db.scalars(select(Environment).where(
        Environment.id.in_({grant.environment_id for grant in grants}))).all()}
    grouped = {user.id: [] for user in people}
    people_by_id = {user.id: user for user in people}
    for grant in grants:
        grouped[grant.user_id].append(grant)
    grant_states = {grant.id: grant_state(grant, people_by_id[grant.user_id], env_objects[grant.environment_id]) for grant in grants}
    grant_groups = [{'user': user, 'grants': grouped[user.id],
                     'visible_grants': [grant for grant in grouped[user.id]
                                        if grant_states[grant.id][0] in ('positive', 'warning')]} for user in people]
    return request.app.state.templates.TemplateResponse(request=request, name='people.html', context={
        'admin': admin, 'csrf': session.csrf, 'tab': 'users', 'page_title': '人员与授权',
        'people': people, 'grants': grants, 'grant_groups': grant_groups,
        'users': users, 'environments': {key: env.name for key, env in env_objects.items()},
        'grant_states': grant_states,
        'available_environments': db.scalars(select(Environment).where(Environment.enabled.is_(True)).order_by(Environment.name)).all(),
        'configurable_environments': db.scalars(select(Environment).where(Environment.enabled.is_(True)).order_by(Environment.name)).all(),
        'count': count, 'page': page, 'q': q, 'status': status, 'grant_status': grant_status, 'saved': saved,
        'stats': overview(db),
        'previous': str(request.url.include_query_params(page=page-1)),
        'next': str(request.url.include_query_params(page=page+1))})
