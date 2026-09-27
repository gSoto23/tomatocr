import pytest

from tests.conftest import new_client

PAGES = ["/", "/proyectos-reforestacion", "/programas/darboles", "/privacidad", "/contacto/gracias"]


@pytest.mark.parametrize("path", PAGES)
def test_public_page_get(path):
    assert new_client().get(path).status_code == 200


@pytest.mark.parametrize("path", PAGES)
def test_public_page_head(path):
    assert new_client().head(path).status_code == 200


@pytest.mark.parametrize("path", ["/robots.txt", "/sitemap.xml", "/api/reforestation/map-data"])
def test_public_resources(path):
    assert new_client().get(path).status_code == 200
