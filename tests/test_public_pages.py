import pytest

from tests.conftest import new_client
from app.utils.servicios import SERVICIOS

PAGES = ["/", "/proyectos-reforestacion", "/programas/darboles", "/privacidad", "/contacto/gracias",
         *(f"/servicios/{slug}" for slug in SERVICIOS)]


@pytest.mark.parametrize("path", PAGES)
def test_public_page_get(path):
    assert new_client().get(path).status_code == 200


@pytest.mark.parametrize("path", PAGES)
def test_public_page_head(path):
    assert new_client().head(path).status_code == 200


@pytest.mark.parametrize("path", ["/robots.txt", "/sitemap.xml", "/api/reforestation/map-data",
                                  "/static/images/hero/siembra-640.jpg", "/static/images/hero/siembra-960.jpg",
                                  *[f"/static/images/proyectos/{name}.jpg" for name in
                                    ("museo-jardin", "alajuela-parque", "vivero", "mantenimiento-residencial")],
                                  *[f"/static/images/servicios/{name}.jpg" for name in
                                    ("reforestacion", "mantenimiento", "jardineria", "paisajismo")]])
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


def test_sales_actions_use_the_brand_green():
    html = new_client().get("/").text
    for label in ("Cotizar\n", "Cotizar por WhatsApp", "Enviar solicitud"):
        start = html.index(label)
        tag = html[html.rindex("<", 0, start):start]
        assert "bg-brand" in tag, label
    css = open("app/static/css/tailwind.css").read()
    assert ".bg-brand{" in css and "bg-brand-light" in css


def test_services_are_photo_cards_that_link_to_their_pages():
    html = new_client().get("/").text
    services = html[html.index('id="services"'):html.index('id="projects"')]
    assert services.count("<article") == 4
    assert services.count('src="/static/images/servicios/') == 4
    for slug in SERVICIOS:
        assert f'href="/servicios/{slug}"' in services
    # The full scope lives on each service page only (no duplicate text on the home)
    assert "<details" not in services and "hidrokeeper (polímeros" not in services
    assert "services-toggle" not in html


@pytest.mark.parametrize("path", ["/", "/programas/darboles", "/proyectos-reforestacion"])
def test_share_image_and_click_tracking(path):
    html = new_client().get(path).text
    assert "https://tomatocr.com/static/images/og-tomato-2026-09.jpg" in html
    assert "og-image.jpg" not in html
    assert "js/analytics.js" in html
    assert new_client().get("/static/images/og-tomato-2026-09.jpg").status_code == 200
    assert new_client().get("/static/js/analytics.js").status_code == 200


# --- SEO quick wins ----------------------------------------------------------------------

import re


@pytest.mark.parametrize("path, keyword", [("/", "Costa Rica"), ("/programas/darboles", "empresas"),
                                           ("/proyectos-reforestacion", "GPS")])
def test_titles_and_descriptions_fit_in_search_results(path, keyword):
    html = new_client().get(path).text
    title = re.search(r"<title>(.*?)</title>", html).group(1)
    description = re.search(r'<meta name="description"\s+content="(.*?)"', html, re.S).group(1)
    assert len(title) <= 60 and keyword in title
    assert len(description) <= 155


def test_map_page_is_readable_without_javascript(db):
    add_project(db, "institucional", [("Cedro", 10.0), ("Roble", 10.1)])
    html = new_client().get("/proyectos-reforestacion").text
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S).group(1)
    assert "Mapa de reforestación" in h1
    assert "Cómo funciona la trazabilidad de cada árbol" in html
    assert re.search(r'x-text="totalTrees">2<', html)  # server figure, not a 0 placeholder
    words = len(re.findall(r"\w+", re.sub(r"<script.*?</script>|<[^>]+>", " ", html, flags=re.S)))
    assert words > 300


def test_home_structured_data_describes_the_business():
    import json
    html = new_client().get("/").text
    data = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S).group(1))
    assert data["@type"] == "LocalBusiness" and data["logo"].startswith("https://tomatocr.com/")
    assert len(data["hasOfferCatalog"]["itemListElement"]) == 4
    assert data["areaServed"]["name"] == "Costa Rica"


def test_public_trailing_slash_redirects_for_good_and_internal_ones_keep_theirs():
    client = new_client()
    response = client.get("/programas/darboles/", follow_redirects=False)
    assert response.status_code == 308 and response.headers["location"].endswith("/programas/darboles")
    assert client.get("/dashboard/", follow_redirects=False).status_code != 308


def test_security_and_cache_headers():
    client = new_client()
    assert "max-age=31536000" in client.get("/").headers["strict-transport-security"]
    assert "immutable" in client.get("/static/css/tailwind.css?v=1").headers["cache-control"]
    assert client.get("/static/images/og-tomato-2026-09.jpg").headers["cache-control"] == "public, max-age=604800"


# --- Service pages -----------------------------------------------------------------------

import json


@pytest.mark.parametrize("slug", list(SERVICIOS))
def test_service_page_is_complete_for_search_and_quotes(slug):
    service = SERVICIOS[slug]
    html = new_client().get(f"/servicios/{slug}").text
    assert len(service["title"]) <= 60 and len(service["description"]) <= 155
    assert f"<title>{service['title']}</title>" in html
    assert f'<link rel="canonical" href="https://tomatocr.com/servicios/{slug}" />' in html
    assert re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S).group(1).strip() == service["h1"]
    graph = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S).group(1))["@graph"]
    assert [g["@type"] for g in graph] == ["Service", "BreadcrumbList", "FAQPage"]
    assert len(graph[2]["mainEntity"]) == len(service["faq"])
    assert f'<option value="{service["motor"]}" selected>' in html  # the form comes with the service chosen
    words = len(re.findall(r"\w+", re.sub(r"<script.*?</script>|<[^>]+>", " ", html, flags=re.S)))
    assert words > 450
    for src, *_ in service["gallery"] + [service["hero"]]:
        assert new_client().get(src).status_code == 200
    for other in SERVICIOS:
        assert f'href="/servicios/{other}"' in html


def test_unknown_service_is_404_and_services_are_in_the_sitemap():
    client = new_client()
    assert client.get("/servicios/no-existe").status_code == 404
    sitemap = client.get("/sitemap.xml").text
    for slug in SERVICIOS:
        assert f"https://tomatocr.com/servicios/{slug}</loc>" in sitemap
    assert client.get("/servicios/jardineria/", follow_redirects=False).status_code == 308


def test_reforestation_service_shows_live_figures(db):
    add_project(db, "institucional", [("Cedro", 10.0)] * 3)
    html = new_client().get("/servicios/reforestacion-para-empresas").text
    assert "Cada árbol, en un mapa público" in html
    assert "Cada árbol, en un mapa público" not in new_client().get("/servicios/jardineria").text


def test_darboles_page_shows_the_catalog_trees_and_campaign_photos():
    html = new_client().get("/programas/darboles").text
    species = re.findall(r'src="(/static/images/darboles/especies/[^"]+)"', html)
    assert len(set(species)) == 12
    assert 'id="especies"' in html and 'href="#especies"' in html
    for src in set(species) | set(re.findall(r'src="(/static/images/darboles/[^"/]+\.jpg)"', html)):
        assert new_client().get(src).status_code == 200
    assert "Compra en la tienda" not in html
    steps = re.findall(r'src="(/static/images/darboles/pasos/[^"]+\.svg)"', html)
    assert len(steps) == 4
    for src in steps:
        assert new_client().get(src).status_code == 200


@pytest.mark.parametrize("path", PAGES)
def test_css_and_js_links_are_versioned(path):
    # Unversioned /static links are cached for 7 days, so a deploy wouldn't reach browsers.
    html = new_client().get(path).text
    for link in re.findall(r'(?:href|src)="(/static/(?:css|js)/[^"]+)"', html):
        assert "?v=" in link, link
