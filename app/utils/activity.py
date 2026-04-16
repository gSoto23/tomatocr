from sqlalchemy.orm import Session
import logging
import json

logger = logging.getLogger(__name__)
from app.db.models.activity import ActivityLog
from app.db.models.user import User

def compute_diff(old_dict: dict, new_dict: dict, tracked_fields: list = None) -> list:
    """
    Computes a list of human-readable differences between two dictionaries.
    Filters by tracked_fields if provided.
    """
    diffs = []
    fields = tracked_fields if tracked_fields else new_dict.keys()
    
    for key in fields:
        if key in new_dict and key in old_dict:
            old_val = old_dict[key]
            new_val = new_dict[key]
            if str(old_val) != str(new_val):
                # Map specific translations for display (Optional improvement)
                display_key = key.replace("_", " ").title()
                diffs.append(f"{display_key}: '{old_val}' a '{new_val}'")
    return diffs

def log_activity(
    db: Session, 
    user: User, 
    action: str, 
    entity_type: str, 
    entity_id: int = None, 
    details=None
):
    """
    Records an activity in the audit log.
    
    :param db: Database session
    :param user: The User object performing the action
    :param action: String describing action (e.g. CREATE, UPDATE, DELETE)
    :param entity_type: String describing resource (e.g. PROJECT, USER)
    :param entity_id: ID of the resource
    :param details: Optional string or json serializable dict/list with more info
    """
    try:
        if isinstance(details, (dict, list)):
            details_str = json.dumps(details, ensure_ascii=False)
        else:
            details_str = str(details) if details else None

        activity = ActivityLog(
            user_id=user.id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details_str,
        )
        db.add(activity)
        db.commit()
    except Exception as e:
        logger.error(f"Error logging activity: {e}")
        db.rollback()
