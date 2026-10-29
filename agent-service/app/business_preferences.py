"""User/environment-scoped preferred tenant, always resolved against fresh catalog."""

import json
from sqlalchemy import select
from .models import UserPreference, Conversation, now


def business_key(business):
    return json.dumps(
        [
            business.get(k, "")
            for k in ("type", "department_id", "tenant_id", "team_id", "businessId")
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def remember(db, user_id, business):
    preference = db.get(UserPreference, user_id)
    if preference is None:
        db.add(UserPreference(user_id=user_id, business=dict(business)))
    else:
        preference.business = dict(business)
        preference.updated_at = now()


def preferred(db, user_id, catalog):
    preference = db.get(UserPreference, user_id)
    if preference:
        previous = preference.business
    else:
        # Bootstrap existing accounts after upgrade from their latest actual conversation.
        conversation = db.scalar(
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
            .limit(1)
        )
        if not conversation:
            return None
        previous = conversation.business
    key = business_key(previous)
    return next((b for b in catalog if business_key(b) == key), None)
