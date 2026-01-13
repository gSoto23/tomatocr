from sqlalchemy.orm import Session
from app.db.models.activity import ActivityLog
from app.db.models.user import User

def log_activity(
    db: Session, 
    user: User, 
    action: str, 
    entity_type: str, 
    entity_id: int = None, 
    details: str = None
):
    """
    Records an activity in the audit log.
    
    :param db: Database session
    :param user: The User object performing the action
    :param action: String describing action (e.g. CREATE, UPDATE, DELETE)
    :param entity_type: String describing resource (e.g. PROJECT, USER)
    :param entity_id: ID of the resource
    :param details: Optional string or textual JSON with more info
    """
    try:
        activity = ActivityLog(
            user_id=user.id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details,
            # ip_address could be passed if we had Request context here, 
            # but for simplicity we skip or require it passed in details if needed.
        )
        db.add(activity)
        db.commit()
    except Exception as e:
        print(f"Error logging activity: {e}")
        # Validate that we don't break the main flow if logging fails
        db.rollback()
