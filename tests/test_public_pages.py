import pytest

from tests.conftest import new_client

PAGES = ["/", "/proyectos-reforestacion", "/programas/darboles", "/privacidad", "/contacto/gracias"]


@pytest.mark.parametrize("path", PAGES)
def test_public_page_get(path):
    assert new_client().get(path).status_code == 200


@pytest.mark.parametrize("path", PAGES)
def test_public_page_head(path):
    assert new_client().head(path).status_code == 200


@pytest.mark.parametrize("path", ["/robots.txt", "/sitemap.xml", "/api/reforestation/map-data",
                                  "/static/images/hero/siembra-640.jpg", "/static/images/hero/siembra-960.jpg",
                                  *[f"/static/images/proyectos/{name}.jpg" for name in
                                    ("museo-jardin", "alajuela-parque", "vivero", "mantenimiento-residencial")]])
def test_public_resources(path):
    assert new_client().get(path).status_code == 200


# --- Home: live reforestation figures ------------------------------------------

from sqlalchemy.exc import OperationalError

from app.db.models.reforestation import KIND_DARBOLES, ReforestationProject, ReforestationTree
from app.utils.reforestation import public_stats


def add_project(db, kind, trees):
    project = ReforestationProject(client_name=f"Proyecto {kind}", kind=kind)
    db.add(project)
    db.flush()
    for number, (species, lat) in enumerate(trees, start=1):
        db.add(ReforestationTree(project_id=project.id, tree_number=number, species=species,
                                 lat=lat, lng=lat and -84.2))
    db.commit()
    return project


def test_public_stats_count_institutional_projects_only(db):
    project = add_project(db, "institucional", [("Cedro", 10.0), ("cedro ", 10.1), ("Guanacaste", None), ("", 10.2)])
    add_project(db, KIND_DARBOLES, [("Roble", 9.9)] * 5)
    # Tree 4 was replaced by a new one: the replacement doesn't count as planted.
    replacement = ReforestationTree(project_id=project.id, tree_number=5, species="Ceiba", lat=10.3, lng=-84.2)
    db.add(replacement)
    db.flush()
    db.query(ReforestationTree).filter_by(project_id=project.id, tree_number=4).update({"replaced_by_id": replacement.id})
    db.commit()

    stats = public_stats(db)
    assert (stats.planted, stats.with_gps, stats.species, stats.projects) == (4, 3, 2, 1)
    assert stats.gps_pct == 75


def test_home_shows_live_figures(db):
    add_project(db, "institucional", [("Cedro", 10.0)] * 1234)
    html = new_client().get("/").text
    assert "En vivo desde nuestro sistema" in html
    assert "1.234" in html


def test_home_hides_figures_without_trees():
    html = new_client().get("/").text
    assert "En vivo desde nuestro sistema" not in html
    assert "Reforestación que podés comprobar" in html


def test_home_loads_when_figures_fail(monkeypatch):
    def broken(db):
        raise OperationalError("SELECT", {}, Exception("no such column"))
    monkeypatch.setattr("app.main.public_stats", broken)
    response = new_client().get("/")
    assert response.status_code == 200
    assert "En vivo desde nuestro sistema" not in response.text


def test_home_has_projects_gallery_in_the_menu():
    html = new_client().get("/").text
    assert 'id="projects"' in html
    assert html.count('href="#projects"') == 2  # desktop bar and phone menu
    assert html.count('src="/static/images/proyectos/') == 4
