from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from omniai.adapters.relational.sqlalchemy.models import AuditEventRecord

logger = logging.getLogger(__name__)


def record_audit_event(
    session: Session,
    *,
    tenant_id: str,
    actor_user_id: str | None,
    action: str,
    target_type: str,
    target_id: str,
    detail: dict[str, Any] | None = None,
) -> None:
    """Persist an audit event. Best-effort: logs and swallows on failure.

    Use as `record_audit_event(session, ...)` from inside a request handler
    after the primary action committed. The session is the same one used by
    the handler — we add+commit the event row on top of any prior state.
    """
    try:
        record = AuditEventRecord(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            detail_json=json.dumps(detail or {}, default=str)[:8000],
        )
        session.add(record)
        session.commit()
    except Exception:
        logger.warning("audit: failed to record event %s/%s", action, target_id, exc_info=True)
        try:
            session.rollback()
        except Exception:
            pass
