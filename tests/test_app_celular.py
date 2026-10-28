"""The installable app: manifest, service worker, the page without connection, and phone
notifications (web push): turning them on and off, the test, and the outbox sending them
(signed and encrypted for real, only the push service's HTTP call is faked)."""
import asyncio
import base64
import json
import os
from datetime import datetime

import pytest
import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from py_vapid import Vapid

from app.core.config import settings
from app.db.models.notification import Notification, PushSubscription
from app.utils import notifications
from app.utils.notifications import deliver, notify
from tests.conftest import new_client
from tests.test_dashboard_tareas import add_task


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


@pytest.fixture
def vapid(monkeypatch):
    keys = Vapid()
    keys.generate_keys()
    private = keys.private_key.private_numbers().private_value.to_bytes(32, "big")
    public = keys.public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    monkeypatch.setattr(settings, "VAPID_PUBLIC_KEY", b64(public))
    monkeypatch.setattr(settings, "VAPID_PRIVATE_KEY", b64(private))
    return b64(public)


def browser_subscription(endpoint="https://fcm.googleapis.com/fcm/send/telefono-1"):
    """What a browser hands the page: its own key pair and auth secret."""
    key = ec.generate_private_key(ec.SECP256R1())
    p256dh = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return {"endpoint": endpoint, "keys": {"p256dh": b64(p256dh), "auth": b64(os.urandom(16))}}


class PushService:
    """Fakes the push service's answer and keeps what it got."""
    def __init__(self, monkeypatch, status=201):
        self.status, self.calls = status, []
        monkeypatch.setattr(requests, "post", self.post)

    def post(self, url, data=None, headers=None, timeout=None, **kwargs):
        self.calls.append({"url": url, "data": data, "headers": headers})
        response = requests.Response()
        response.status_code = self.status if not callable(self.status) else self.status(url)
        response._content = b""
        return response


def turn_on(client, subscription):
    return client.post("/notificaciones/push", json=subscription)


# --- The app ----------------------------------------------------------------------

def test_manifest_and_service_worker():
    client = new_client()
    manifest = client.get("/manifest.webmanifest")
    assert manifest.status_code == 200 and manifest.headers["content-type"].startswith("application/manifest+json")
    data = manifest.json()
    assert data["display"] == "standalone" and data["start_url"] == "/dashboard/" and data["scope"] == "/"
    for icon in data["icons"]:
        assert client.get(icon["src"]).status_code == 200
    assert {"512x512"} <= {i["sizes"] for i in data["icons"]} and any(i.get("purpose") == "maskable" for i in data["icons"])
    sw = client.get("/sw.js")
    assert sw.status_code == 200 and "javascript" in sw.headers["content-type"] and sw.headers["cache-control"] == "no-cache"
    assert 'addEventListener("push"' in sw.text and 'addEventListener("notificationclick"' in sw.text
    assert "Sin conexión" in client.get("/offline").text


def test_the_dashboard_links_the_app(login_as, users):
    page = login_as("worker").get("/dashboard/").text
    assert '<link rel="manifest" href="/manifest.webmanifest">' in page
    assert 'serviceWorker.register("/sw.js")' in page and 'apple-mobile-web-app-capable' in page


# --- Turning it on ----------------------------------------------------------------

def test_without_keys_the_page_says_so_and_nothing_is_saved(db, login_as, users):
    worker = login_as("worker")
    assert "phonePush('', 0)" in worker.get("/notificaciones").text
    assert turn_on(worker, browser_subscription()).status_code == 503
    assert db.query(PushSubscription).count() == 0


def test_turning_it_on_and_off(db, login_as, users, vapid):
    worker = login_as("worker")
    assert f"phonePush('{vapid}', 0)" in worker.get("/notificaciones").text
    subscription = browser_subscription()
    assert turn_on(worker, subscription).json() == {"ok": True}
    assert turn_on(worker, subscription).json() == {"ok": True}  # the same phone twice is one device
    device = db.query(PushSubscription).one()
    assert device.user_id == users["worker"].id and device.auth == subscription["keys"]["auth"]
    assert f"phonePush('{vapid}', 1)" in worker.get("/notificaciones").text
    worker.post("/notificaciones/push/quitar", json={"endpoint": subscription["endpoint"]})
    assert db.query(PushSubscription).count() == 0


def test_a_phone_moves_to_who_signs_in_on_it(db, login_as, users, vapid):
    subscription = browser_subscription()
    turn_on(login_as("worker"), subscription)
    turn_on(login_as("ventas"), subscription)
    db.expire_all()
    assert db.query(PushSubscription).one().user_id == users["ventas"].id


def test_nobody_turns_off_someone_elses(db, login_as, users, vapid):
    subscription = browser_subscription()
    turn_on(login_as("worker"), subscription)
    login_as("ventas").post("/notificaciones/push/quitar", json={"endpoint": subscription["endpoint"]})
    assert db.query(PushSubscription).count() == 1


def test_bad_subscriptions_and_the_client_are_refused(db, login_as, users, vapid):
    worker = login_as("worker")
    assert turn_on(worker, {"endpoint": "http://inseguro", "keys": {"p256dh": "x", "auth": "y"}}).status_code == 400
    assert turn_on(worker, {"endpoint": "https://fcm.googleapis.com/x"}).status_code == 400
    assert turn_on(login_as("client"), browser_subscription()).status_code == 403
    assert db.query(PushSubscription).count() == 0


# --- Sending ----------------------------------------------------------------------

def test_an_assigned_task_rings_the_phone(db, login_as, users, vapid, monkeypatch):
    service = PushService(monkeypatch)
    turn_on(login_as("worker"), browser_subscription())
    add_task(login_as("supervisor"), [users["worker"].id], title="Regar el vivero", description="Con la manguera nueva")
    notice = db.query(Notification).one()
    assert notice.push_status == "sent" and notice.pushed_at is not None
    call = service.calls[0]
    assert call["url"] == "https://fcm.googleapis.com/fcm/send/telefono-1"
    assert call["headers"]["Authorization"].startswith("vapid t=") and call["headers"]["Content-Encoding"] == "aes128gcm"
    assert call["data"] and b"Regar el vivero" not in call["data"]  # encrypted
    message = notifications.push_message(notice)
    assert message["title"] == "Tarea asignada: Regar el vivero" and message["url"] == f"/notificaciones/{notice.id}/ir"
    assert "Con la manguera nueva" in message["body"]


def test_without_a_phone_nothing_is_pending(db, login_as, users, vapid):
    add_task(login_as("supervisor"), [users["worker"].id])
    assert db.query(Notification).one().push_status == "none"


def test_a_phone_that_is_gone_is_deleted(db, login_as, users, vapid, monkeypatch):
    PushService(monkeypatch, status=410)
    turn_on(login_as("worker"), browser_subscription())
    add_task(login_as("supervisor"), [users["worker"].id])
    assert db.query(Notification).one().push_status == "none"
    assert db.query(PushSubscription).count() == 0


def test_a_push_failure_is_retried(db, login_as, users, vapid, monkeypatch):
    service = PushService(monkeypatch, status=500)
    turn_on(login_as("worker"), browser_subscription())
    add_task(login_as("supervisor"), [users["worker"].id])
    notice = db.query(Notification).one()
    assert (notice.push_status, notice.push_attempts) == ("pending", 1)
    service.status = 201
    asyncio.run(deliver())
    db.expire_all()
    assert db.get(Notification, notice.id).push_status == "sent" and len(service.calls) == 2


def test_one_working_phone_is_enough(db, login_as, users, vapid, monkeypatch):
    PushService(monkeypatch, status=lambda url: 201 if url.endswith("bueno") else 500)
    worker = login_as("worker")
    turn_on(worker, browser_subscription("https://fcm.googleapis.com/fcm/send/bueno"))
    turn_on(worker, browser_subscription("https://fcm.googleapis.com/fcm/send/malo"))
    add_task(login_as("supervisor"), [users["worker"].id])
    assert db.query(Notification).one().push_status == "sent"


def test_already_read_in_the_bell_does_not_ring(db, users, vapid, monkeypatch):
    service = PushService(monkeypatch)
    db.add(PushSubscription(user_id=users["worker"].id, **{"endpoint": "https://fcm.googleapis.com/x",
                                                          "p256dh": browser_subscription()["keys"]["p256dh"],
                                                          "auth": b64(os.urandom(16))}))
    db.commit()
    notice = notify(db, users["worker"], "task_assigned", "Prueba")
    db.commit()
    notice.read_at = datetime.utcnow()
    db.commit()
    asyncio.run(deliver())
    db.expire_all()
    assert db.get(Notification, notice.id).push_status == "none" and service.calls == []


def test_at_night_only_urgent_ones_ring(db, login_as, users, vapid, monkeypatch):
    service = PushService(monkeypatch)
    moment = datetime.combine(datetime.utcnow().date(), datetime.min.time()).replace(hour=23)
    monkeypatch.setattr(notifications, "now_cr", lambda: moment)
    turn_on(login_as("worker"), browser_subscription())
    supervisor = login_as("supervisor")
    add_task(supervisor, [users["worker"].id], title="Normal")
    add_task(supervisor, [users["worker"].id], title="Urgente", priority="alta")
    assert len(service.calls) == 1
    assert db.query(Notification).filter_by(push_status="pending").count() == 1


def test_the_test_button(db, login_as, users, vapid, monkeypatch):
    service = PushService(monkeypatch)
    worker = login_as("worker")
    assert worker.post("/notificaciones/push/prueba").json() == {"ok": False}  # no phone yet
    turn_on(worker, browser_subscription())
    assert worker.post("/notificaciones/push/prueba").json() == {"ok": True}
    assert len(service.calls) == 1 and db.query(Notification).count() == 0


def test_tapping_the_phone_notification_opens_it(db, login_as, users):
    add_task(login_as("supervisor"), [users["worker"].id])
    notice = db.query(Notification).one()
    worker = login_as("worker")
    response = worker.get(f"/notificaciones/{notice.id}/ir", follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/dashboard/"
    db.expire_all()
    assert db.get(Notification, notice.id).read_at is not None
    assert login_as("ventas").get(f"/notificaciones/{notice.id}/ir").status_code == 404


def test_push_message_is_short(db, users):
    notice = notify(db, users["worker"], "task_assigned", "Título", "x " * 200)
    db.commit()
    message = notifications.push_message(notice)
    assert len(message["body"]) <= 181 and message["body"].endswith("…")
    assert json.dumps(message)


def test_cotizar_is_in_the_phone_menu_not_the_header(login_as, users):
    """The phone header only has the bell, ? and ☰; Cotizar is in the menu, hidden on the computer."""
    import re
    page = login_as("ventas").get("/dashboard/").text
    phone_header = page.split("<!-- Mobile Header -->")[1].split("<!-- Mobile Sidebar Overlay -->")[0]
    assert "/cotizador" not in phone_header
    menu_link = re.search(r'<a href="/cotizador" data-menu-cotizar\s+class="md:hidden', page)
    assert menu_link
    computer_header = page.split("<!-- Main Header (Desktop) -->")[1].split("<!-- Main Content -->")[0]
    assert 'href="/cotizador"' in computer_header
    assert "data-menu-cotizar" not in login_as("worker").get("/dashboard/").text


def test_the_logo_goes_to_the_dashboard(login_as, users):
    import re
    page = login_as("worker").get("/projects").text
    links = re.findall(r'<a href="([^"]+)"[^>]*data-logo-home>', page)
    assert links == ["/dashboard", "/dashboard"]  # phone header and side menu


def test_the_digest_rings_the_phone(db, login_as, users, vapid, monkeypatch):
    from datetime import time
    from app.utils.notifications import run_once
    from tests.test_dashboard_tareas import TODAY
    service = PushService(monkeypatch)
    worker = login_as("worker")
    turn_on(worker, browser_subscription())
    add_task(worker, title="Regar")
    moment = datetime.combine(TODAY, time(7, 0))
    monkeypatch.setattr(notifications, "now_cr", lambda: moment)
    asyncio.run(run_once())
    notice = db.query(Notification).filter_by(kind="daily_digest").one()
    assert notice.push_status == "sent" and len(service.calls) == 1
