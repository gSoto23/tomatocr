"""User manual: each role sees only its chapters, the "?" opens the right one, and every
screenshot a chapter uses exists."""
import re
from pathlib import Path

import pytest

from app.utils.manual import BY_SLUG, CHAPTERS, chapters_for, help_url

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "app" / "templates" / "manual"
STATIC = ROOT / "app" / "static" / "manual"

VISIBLE = {
    "admin": {"primeros-pasos", "dashboard", "proyectos", "calendario", "planilla", "clientes", "cotizador",
              "presupuestos", "reforestacion", "empleados", "actividad", "recorridos"},
    "ventas": {"primeros-pasos", "dashboard", "clientes", "cotizador", "recorridos"},
    "supervisor": {"primeros-pasos", "dashboard", "proyectos", "calendario", "planilla", "reforestacion", "recorridos"},
    "worker": {"primeros-pasos", "dashboard", "proyectos", "calendario", "planilla", "reforestacion", "recorridos"},
    "client": {"primeros-pasos", "dashboard", "proyectos", "cotizador", "presupuestos", "recorridos"},
}


@pytest.mark.parametrize("role", VISIBLE)
def test_each_role_sees_its_chapters(role, login_as):
    client = login_as(role)
    index = client.get("/manual")
    assert index.status_code == 200
    listed = set(re.findall(r'href="/manual/([a-z-]+)"', index.text))
    assert listed == VISIBLE[role]
    for chapter in CHAPTERS:
        response = client.get(f"/manual/{chapter.slug}")
        assert response.status_code == (200 if chapter.slug in VISIBLE[role] else 404), (role, chapter.slug)


def test_manual_needs_a_session():
    from tests.conftest import new_client
    assert new_client().get("/manual", follow_redirects=False).status_code in (302, 303, 401)


@pytest.mark.parametrize("path,role,url", [
    ("/projects/3", "worker", "/manual/proyectos"),
    ("/logs/new", "supervisor", "/manual/proyectos"),
    ("/clientes/cuentas/1", "ventas", "/manual/clientes"),
    ("/dashboard", "client", "/manual/dashboard"),
    ("/dashboard/activity", "admin", "/manual/actividad"),
    ("/clientes", "worker", "/manual"),  # not their chapter: the index
    ("/payroll/approval", "supervisor", "/manual/planilla"),
    ("/liquidation/history/3", "admin", "/manual/planilla"),
    ("/finance/2", "client", "/manual/presupuestos"),
    ("/finance/2", "supervisor", "/manual"),
    ("/projects/4/monitoreo", "worker", "/manual/reforestacion"),
    ("/projects/4", "worker", "/manual/proyectos"),
    ("/users/9/edit", "admin", "/manual/empleados"),
    ("/calendar", "worker", "/manual/calendario"),
])
def test_help_button_url(path, role, url):
    assert help_url(path, role) == url


def test_help_button_is_on_every_internal_page(login_as):
    for role, path in (("admin", "/dashboard"), ("worker", "/projects"), ("ventas", "/clientes"),
                       ("ventas", "/cotizador")):
        html = login_as(role).get(path).text
        assert "data-help-button" in html, (role, path)
    assert 'href="/manual/clientes"' in login_as("ventas").get("/clientes").text


def test_chapter_sections_match_the_templates():
    for chapter in CHAPTERS:
        html = (TEMPLATES / f"{chapter.slug}.html").read_text()
        anchors = re.findall(r'm\.section\("([a-z-]+)"', html)
        assert anchors == [a for a, _ in chapter.sections], chapter.slug


def test_every_screenshot_exists():
    used = set()
    for template in TEMPLATES.glob("*.html"):
        used |= set(re.findall(r'm\.shot\("([^"]+)"', template.read_text()))
    missing = sorted(src for src in used if not (STATIC / src).exists())
    assert not missing, f"Capturas que faltan: {missing} (scripts/manual/README.md)"


def test_chapters_have_no_formal_usted():
    for template in TEMPLATES.glob("*.html"):
        text = template.read_text()
        for formal in ("usted", "Escriba ", "Elija ", "Indique ", "Revise ", "Intente "):
            assert formal not in text, (template.name, formal)


def test_registry_has_no_duplicate_slugs():
    assert len(BY_SLUG) == len(CHAPTERS) and chapters_for("nadie") == []
