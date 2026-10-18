"""One-shot authentication scenarios shared across processes."""
import json
from .storage import Store


def initial_expiry(root):
    if json.loads((root/'workspace.json').read_text())['scenario'] != 'expired-session':
        return False
    with Store(root).transaction() as db:
        if db.execute("SELECT 1 FROM meta WHERE key='expiry_used'").fetchone():
            return False
        db.execute("INSERT INTO meta VALUES('expiry_used','1')")
        return True
