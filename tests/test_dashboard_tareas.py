"""Dashboard: the person's own tasks (with assigning for admin and supervisor), the "Hoy" block,
and alerts ordered by importance that can be marked "ya lo vi" and go to Pendientes."""
from datetime import date, datetime, timedelta

import pytest

from app.db.models.finance import BudgetLine, Invoice, InvoiceStatus, ProjectBudget
from app.db.models.schedule import ProjectSchedule
from app.db.models.task import AlertAck, Task
from app.utils.admin_overview import LEVELS
from app.utils.timecr import today_cr

TODAY = today_cr()


def add_task(client, **fields):
    data = {"title": "Llamar al vivero", "due_date": TODAY.isoformat(), "priority": "normal"}
    data.update(fields)
    return client.post("/dashboard/tareas", data=data, follow_redirects=False)


# --- Tareas ----------------------------------------------------------------------

def test_a_task_needs_a_title_and_a_date(db, login_as):
    client = login_as("worker")
    add_task(client, title=" ")
    add_task(client, due_date="")
    assert db.query(Task).count() == 0
    assert add_task(client).status_code == 303
    task = db.query(Task).one()
    assert task.assignee_id == task.created_by_id and task.priority == "normal"


def test_today_shows_late_and_today_tasks_first(db, login_as, users):
    client = login_as("ventas")
    add_task(client, title="Tarea de hoy", priority="baja")
    add_task(client, title="Tarea atrasada", due_date=(TODAY - timedelta(days=2)).isoformat())
    add_task(client, title="Tarea urgente de hoy", priority="alta")
    add_task(client, title="Tarea de la otra semana", due_date=(TODAY + timedelta(days=3)).isoformat())
    add_task(client, title="Tarea lejana", due_date=(TODAY + timedelta(days=30)).isoformat())
    html = client.get("/dashboard/").text
    hoy = html.split('aria-labelledby="hoy"', 1)[1].split('aria-labelledby="atencion"', 1)[0]
    assert hoy.index("Tarea atrasada") < hoy.index("Tarea urgente de hoy") < hoy.index("Tarea de hoy")
    assert "Atrasada" in hoy and "Próximos 7 días (1)" in hoy and "Tarea lejana" not in hoy
    assert "3 tareas para hoy" in html


def test_done_moves_to_done_today_and_back(db, login_as):
    client = login_as("worker")
    add_task(client)
    task = db.query(Task).one()
    client.post(f"/dashboard/tareas/{task.id}/hecha")
    db.refresh(task)
    assert task.done_at is not None
    assert "Hechas hoy (1)" in client.get("/dashboard/").text
    client.post(f"/dashboard/tareas/{task.id}/hecha")
    db.refresh(task)
    assert task.done_at is None


def test_edit_and_delete_only_by_the_owner(db, login_as):
    add_task(login_as("worker"), title="Mía")
    task = db.query(Task).one()
    assert login_as("ventas").post(f"/dashboard/tareas/{task.id}/hecha").status_code == 403
    login_as("worker").post(f"/dashboard/tareas/{task.id}/editar", data={
        "title": "Mía, cambiada", "due_date": TODAY.isoformat(), "priority": "alta", "description": "ver https://tomatocr.com"})
    db.refresh(task)
    assert (task.title, task.priority) == ("Mía, cambiada", "alta")
    assert 'href="https://tomatocr.com"' in login_as("worker").get("/dashboard/").text
    login_as("worker").post(f"/dashboard/tareas/{task.id}/borrar")
    assert db.query(Task).count() == 0


def test_admin_and_supervisor_assign_tasks_the_rest_cannot(db, login_as, users):
    add_task(login_as("supervisor"), title="Revisar la motoguadaña", assignee_id=users["worker"].id)
    task = db.query(Task).one()
    assert task.assignee_id == users["worker"].id and task.created_by_id == users["supervisor"].id
    worker_page = login_as("worker").get("/dashboard/").text
    assert "Revisar la motoguadaña" in worker_page and "te la asignó" in worker_page
    assert "Que asigné a otros (1)" in login_as("supervisor").get("/dashboard/").text
    add_task(login_as("worker"), title="Para el admin", assignee_id=users["admin"].id)
    assert db.query(Task).filter(Task.title == "Para el admin").count() == 0
    assert 'name="assignee_id"' not in worker_page
    assert add_task(login_as("admin"), title="Para cliente", assignee_id=users["client"].id).status_code == 303
    assert db.query(Task).filter(Task.title == "Para cliente").count() == 0


def test_clients_have_no_tasks(login_as):
    client = login_as("client")
    assert "Mis tareas" not in client.get("/dashboard/").text
    assert add_task(client).status_code == 403


def test_description_is_escaped(db, login_as):
    add_task(login_as("worker"), description='<script>alert(1)</script> https://x.cr/"onmouseover=1')
    html = login_as("worker").get("/dashboard/").text
    assert "<script>alert(1)</script>" not in html and 'href="https://x.cr/"' in html


# --- Alertas ---------------------------------------------------------------------

@pytest.fixture
def overdue(db, users):
    budget = ProjectBudget(project_id=users["project_id"])
    db.add(budget)
    db.flush()
    line = BudgetLine(budget_id=budget.id, name="Mantenimiento", subtotal=1000)
    db.add(line)
    db.flush()

    def invoice(number):
        db.add(Invoice(budget_id=budget.id, budget_line_id=line.id, invoice_number=number, amount=100,
                       issue_date=TODAY - timedelta(days=40), due_date=TODAY - timedelta(days=10),
                       status=InvoiceStatus.PENDING))
        db.commit()
    invoice("FE-1")
    return invoice


def attention(html):
    return html.split('aria-labelledby="atencion"', 1)[1].split("</section>", 1)[0]


def test_alerts_go_from_most_to_least_important(db, login_as, users, overdue):
    users["worker"].email = ""  # an active person without e-mail: "para revisar"
    db.commit()
    html = attention(login_as("admin").get("/dashboard/").text)
    assert html.index("Urgente") < html.index("Para revisar")
    assert "1 factura vencida" in html
    assert list(LEVELS) == ["urgente", "importante", "revisar"]


def test_seen_alert_goes_to_pending_and_comes_back_when_worse(db, login_as, overdue):
    admin = login_as("admin")
    admin.post("/dashboard/alertas/facturas_vencidas/visto")
    html = attention(admin.get("/dashboard/").text)
    assert "Pendientes (1)" in html and "Volver a mostrar" in html
    new_part = html.split("x-show=\"tab === 'pendientes'\"", 1)[0]
    assert "factura vencida" not in new_part
    overdue("FE-2")  # it got worse
    html = attention(admin.get("/dashboard/").text)
    assert "Pendientes (0)" in html and "2 facturas vencidas" in html.split("x-show=\"tab === 'pendientes'\"", 1)[0]


def test_seen_is_personal_and_goes_away_when_solved(db, login_as, users, overdue):
    login_as("admin").post("/dashboard/alertas/facturas_vencidas/visto")
    assert db.query(AlertAck).count() == 1
    db.query(Invoice).update({Invoice.status: InvoiceStatus.PAID})
    db.commit()
    html = attention(login_as("admin").get("/dashboard/").text)
    assert "factura vencida" not in html and "Pendientes (0)" in html
    assert db.query(AlertAck).count() == 0  # solved: the mark is gone


def test_back_to_new(db, login_as, overdue):
    admin = login_as("admin")
    admin.post("/dashboard/alertas/facturas_vencidas/visto")
    admin.post("/dashboard/alertas/facturas_vencidas/volver")
    assert "Pendientes (0)" in attention(admin.get("/dashboard/").text)


def test_worker_and_sales_have_their_own_alerts(db, login_as, users):
    db.add(ProjectSchedule(project_id=users["project_id"], user_id=users["worker"].id, date=TODAY - timedelta(days=1)))
    db.commit()
    worker = login_as("worker")
    assert "Te quedó 1 día sin bitácora" in attention(worker.get("/dashboard/").text)
    worker.post("/dashboard/alertas/mis_dias_sin_bitacora/visto")
    assert "Pendientes (1)" in attention(worker.get("/dashboard/").text)
    admin = attention(login_as("admin").get("/dashboard/").text)
    assert "día trabajado sin bitácora" in admin and "Pendientes (0)" in admin  # the worker's mark is only theirs
