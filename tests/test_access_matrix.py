"""Access matrix by role and route (docs/PLAN_SISTEMA_COMERCIAL.md, Fase 0).

The admin/supervisor/worker/client columns were recorded against the code
before Fase 0, so they guard against behavior changes for existing roles.
"303" means a redirect (to the dashboard, to "/" or to the user's own page).
"""
import pytest

ROLE_ORDER = ["admin", "supervisor", "worker", "client", "ventas"]

# route: expected status for (admin, supervisor, worker, client, ventas)
MATRIX = {
    "/dashboard/":                     (200, 200, 200, 200, 200),
    "/dashboard/activity":             (200, 303, 303, 303, 303),
    "/projects/":                      (200, 200, 200, 200, 403),
    "/projects/{project}":             (200, 200, 200, 200, 403),
    "/finance/":                       (200, 200, 403, 200, 403),
    "/finance/{project}":              (200, 200, 403, 200, 403),
    "/payroll/":                       (200, 200, 200, 403, 403),
    "/payroll/approval":               (200, 200, 403, 403, 403),
    "/payroll/supervisor/projects":    (200, 200, 403, 403, 403),
    "/payments/":                      (200, 303, 303, 303, 403),
    "/payments/history/{me}":          (200, 200, 200, 200, 403),
    "/liquidation/":                   (200, 303, 303, 303, 403),
    "/liquidation/history/{me}":       (200, 200, 200, 200, 403),
    "/calendar/":                      (200, 200, 200, 303, 403),
    "/calendar/events?start=2026-01-01&end=2026-12-31": (200, 200, 200, 200, 403),
    "/logs/":                          (200, 200, 200, 200, 403),
    "/logs/new":                       (200, 200, 200, 303, 403),
    "/users/":                         (200, 403, 403, 403, 403),
    "/users/new":                      (200, 403, 403, 403, 403),
    "/cotizador":                      (200, 403, 403, 200, 200),
    "/api/quotes/":                    (200, 403, 403, 200, 200),
    "/api/quotes/next-number":         (200, 403, 403, 200, 200),
    "/dashboard/reforestacion":        (200, 403, 403, 403, 403),
}

CASES = [
    (role, route, codes[i])
    for route, codes in MATRIX.items()
    for i, role in enumerate(ROLE_ORDER)
]


@pytest.mark.parametrize("role,route,expected", CASES, ids=[f"{r}:{p}" for r, p, _ in CASES])
def test_access_matrix(role, route, expected, users, login_as):
    client = login_as(role)
    path = route.format(project=users["project_id"], me=users[role].id)
    response = client.get(path, follow_redirects=False)
    assert response.status_code == expected


@pytest.mark.parametrize("path", ["/finance/{project}/invoice", "/payroll/generate", "/users/new"])
def test_ventas_cannot_post_to_restricted_modules(path, users, login_as):
    client = login_as("ventas")
    response = client.post(path.format(project=users["project_id"]), data={}, follow_redirects=False)
    assert response.status_code == 403


def test_ventas_menu_shows_only_dashboard_and_quotes(users, login_as):
    html = login_as("ventas").get("/dashboard/").text
    assert 'href="/cotizador"' in html
    for hidden in ['href="/projects"', 'href="/finance"', 'href="/payroll"', 'href="/calendar"', 'href="/users"']:
        assert hidden not in html
