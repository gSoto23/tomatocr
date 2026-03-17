import logging
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from app.db.models.activity import ActivityLog

logger = logging.getLogger(__name__)

def log_activity(
    db: Session,
    user_id: int,
    action: str,
    entity_type: str = None,
    entity_id: int = None,
    details: str = None,
    ip_address: str = None
):
    """
    Helper to record a user activity in the activity_logs table.
    """
    try:
        audit_record = ActivityLog(
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details,
            ip_address=ip_address
        )
        db.add(audit_record)
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Failed to record audit log for action {action}: {e}")
