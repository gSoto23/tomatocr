"""Confirmations use the system's own window (components/confirm_modal.html), never the
browser's confirm() / prompt(), and a cancelled form doesn't leave the "Cargando" screen on."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sources():
    files = list((ROOT / "app" / "templates").rglob("*.html")) + [ROOT / "app" / "static" / "cotizador" / "app.js"]
    return {f: f.read_text() for f in files}


def test_no_browser_confirm_or_prompt_left():
    native = re.compile(r"(?<![\w.])(confirm|prompt)\(")
    offenders = [f"{f.relative_to(ROOT)}:{n}" for f, text in sources().items() if f.name != "confirm_modal.html"
                 for n, line in enumerate(text.splitlines(), 1) if native.search(line)]
    assert offenders == []


def test_pages_carry_the_window(login_as):
    html = login_as("admin").get("/dashboard/").text
    assert 'id="tomato-confirm"' in html and "window.tomatoConfirm" in html
    assert "if (!e.defaultPrevented) showLoader()" in html  # cancelled: no loader
    assert 'id="tomato-confirm"' in login_as("ventas").get("/cotizador").text


def test_delete_forms_ask_with_the_window(db, login_as):
    client = login_as("worker")
    from app.utils.timecr import today_cr
    client.post("/dashboard/tareas", data={"title": "Probar", "due_date": today_cr().isoformat()})
    html = client.get("/dashboard/").text
    assert 'data-confirm="¿Borrar la tarea?" data-confirm-ok="Borrar"' in html


def test_messages_are_escaped(db, login_as):
    from app.db.models.supplier import Supplier
    db.add(Supplier(name='Vivero "El <b>Roble</b>"'))
    db.commit()
    html = login_as("admin").get("/proveedores/1").text
    assert 'data-confirm="¿Borrar «Vivero &#34;El &lt;b&gt;Roble&lt;/b&gt;&#34;» y sus contactos?"' in html
