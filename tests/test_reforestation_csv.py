from datetime import date
from urllib.parse import unquote

import pytest

from app.db.models.reforestation import ReforestationProject, ReforestationTree


@pytest.mark.parametrize("client_name,ascii_name", [
    ("Árbol ñandú", "Arbol_nandu_inventario.csv"),
    ("Museo de Arte Costarricense", "Museo_de_Arte_Costarricense_inventario.csv"),
])
def test_csv_download_with_any_client_name(db, login_as, client_name, ascii_name):
    project = ReforestationProject(client_name=client_name)
    project.trees = [ReforestationTree(tree_number=1, species="Guanacaste", sector_name="Sector Á",
                                       lat=10.01, lng=-84.21, date_planted=date(2026, 6, 1))]
    db.add(project)
    db.commit()

    response = login_as("admin").get(f"/dashboard/reforestacion/download-csv/{project.id}")

    assert response.status_code == 200
    assert response.text.splitlines() == [
        "TreeNumber,Species,Sector,Lat,Lng,Date",
        "1,Guanacaste,Sector Á,10.01,-84.21,2026-06-01",
    ]
    disposition = response.headers["content-disposition"]
    assert disposition.startswith(f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'')
    encoded = disposition.split("filename*=UTF-8''", 1)[1]
    assert unquote(encoded) == f"{client_name.replace(' ', '_')}_inventario.csv"


def test_download_link_does_not_trigger_the_page_loader(db, login_as):
    project = ReforestationProject(client_name="Municipalidad Alajuela")
    db.add(project)
    db.commit()
    html = login_as("admin").get("/dashboard/reforestacion").text
    # The dashboard loader skips links with the download attribute.
    assert f'href="/dashboard/reforestacion/download-csv/{project.id}" download' in html
    assert "!this.hasAttribute('download')" in html
