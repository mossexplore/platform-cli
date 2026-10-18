"""Local authentication; never opens browsers or reads production state."""
from wiserec_cli.auth import AuthManager
from wiserec_cli.business import Department, Tenant, Team
from wiserec_cli.models import Credentials
from wiserec_cli.output import print_result
from .seeds import uid, business_ids


class DemoAuth(AuthManager):
    def __init__(self, config, store, business_store):
        super().__init__(config, store, business_store)
        self.browser = self

    def login(self, show_secrets=False, **kwargs):
        profile = kwargs.get('profile') or self.config.current_profile()
        import json
        username = json.loads((self.config.path.parent/'workspace.json').read_text()).get('username', 'demo')
        ids = business_ids(profile.name)
        catalog = tuple(Department(uid('department', index+1), name, (
            Tenant(ids[index*3], '推荐业务' if index == 0 else '搜索业务', (),
                   tuple(Team(t, t, f'团队 {i+1}', 'available', t)
                         for i, t in enumerate(ids[index*3+1:index*3+3]))),))
            for index, name in enumerate(('推荐技术部', '搜索技术部')))
        self.business_store.refresh(profile.name, username, catalog, browser_business_id=ids[1])
        credentials = Credentials.create(profile.name, 'demo-session', 'demo-csrf', username,
                                         self.config.auth_ttl_seconds, cn_name='演示用户', department='推荐技术部')
        from .execution_state import initial_expiry
        if initial_expiry(self.config.path.parent):
            from dataclasses import replace
            credentials = replace(credentials, expires_at=0)
        self.store.save(credentials)
        print_result({'环境': profile.name, '账号': username, '中文名': '演示用户'})
        return credentials

    def ensure_credentials(self, force_refresh=False):
        credentials = self.store.load(self.config.current_name)
        if credentials is None or credentials.is_expired() or force_refresh:
            from contextlib import redirect_stdout
            import sys
            with redirect_stdout(sys.stderr):
                return self.login()
        return credentials
