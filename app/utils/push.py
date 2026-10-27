"""Phone notifications (web push) to the devices each person turned on (PushSubscription).
Signed with the VAPID keys in .env; without them there is no push and nothing breaks.
docs/NOTIFICACIONES.md."""
import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Optional

from pywebpush import WebPushException, webpush
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models.notification import PushSubscription

logger = logging.getLogger(__name__)

# How long the push service keeps it if the phone is off (seconds).
TTL = 24 * 3600


def configured() -> bool:
    return bool(settings.VAPID_PUBLIC_KEY and settings.VAPID_PRIVATE_KEY)


def has_devices(db: Session, user_id: int) -> bool:
    return configured() and db.query(PushSubscription.id).filter(PushSubscription.user_id == user_id).first() is not None


def _send_one(subscription: PushSubscription, data: str) -> str:
    """ok, gone (the browser dropped it: delete it) or error (try again later)."""
    try:
        webpush(subscription_info={"endpoint": subscription.endpoint,
                                   "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth}},
                data=data, vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={"sub": settings.VAPID_SUBJECT}, ttl=TTL, timeout=10)
        return "ok"
    except WebPushException as e:
        status = e.response.status_code if e.response is not None else None
        if status in (404, 410):
            return "gone"
        logger.error(f"Push failed ({status}): {e}")
        return "error"
    except Exception as e:
        logger.error(f"Push failed: {e}")
        return "error"


async def push_to(db: Session, user_id: int, message: Dict) -> Optional[bool]:
    """Sends it to every device of this person. True if at least one got it, False if all failed
    (try again later), None if there is nowhere to send it (no devices, or all gone)."""
    if not configured():
        return None
    devices = db.query(PushSubscription).filter(PushSubscription.user_id == user_id).all()
    if not devices:
        return None
    data = json.dumps(message)
    results = [await asyncio.to_thread(_send_one, device, data) for device in devices]
    for device, result in zip(devices, results):
        if result == "gone":
            db.delete(device)
        elif result == "ok":
            device.last_used_at = datetime.utcnow()
    db.commit()
    if "ok" in results:
        return True
    return False if "error" in results else None


def save_device(db: Session, user_id: int, endpoint: str, p256dh: str, auth: str, user_agent: Optional[str]):
    """Turns notifications on for this device. The same device (endpoint) moves to whoever
    turned it on last, e.g. after someone else signs in on that phone."""
    device = db.query(PushSubscription).filter(PushSubscription.endpoint == endpoint).first() \
        or PushSubscription(endpoint=endpoint)
    device.user_id, device.p256dh, device.auth = user_id, p256dh, auth
    device.user_agent = (user_agent or "")[:300] or None
    db.add(device)
