"""How a notification looks: its text read as pieces, the one-line summary for the phone and
the bell, and the designed e-mail (with its plain-text version)."""
from app.utils.notice_format import blocks, email_html, heading, summary
from tests.test_dashboard_tareas import add_task

TASK = ("Gerardo Soto te asignó una tarea.\n\nTarea: Revisar el riego\nVence: 29/10/2026\nPrioridad: Alta\n"
        "Junto con: Will Perez\n\nLlevar la llave: está en la bodega.")
DIGEST = ("Tareas de hoy y atrasadas (2):\n- Reporte Karen (atrasada)\n- Orden de pedido [Alta] (atrasada)\n\n"
          "Urgente:\n- 2 facturas vencidas: Casa Guácima")


def test_the_text_as_pieces():
    parts = blocks(TASK)
    assert [b.kind for b in parts] == ["text", "rows", "text"]
    assert parts[1].rows == [("Tarea", "Revisar el riego"), ("Vence", "29/10/2026"), ("Prioridad", "Alta"),
                             ("Junto con", "Will Perez")]
    assert parts[2].text == "Llevar la llave: está en la bodega."  # a sentence with ":" stays text
    digest = blocks(DIGEST)
    assert [(b.kind, b.text) for b in digest] == [("list", "Tareas de hoy y atrasadas (2)"), ("list", "Urgente")]
    assert [(i.text, i.flags) for i in digest[0].items] == [("Reporte Karen", ["Atrasada"]),
                                                          ("Orden de pedido", ["Alta", "Atrasada"])]


def test_summary_and_heading():
    assert summary(TASK) == ("Gerardo Soto te asignó una tarea · Vence 29/10/2026 · Prioridad alta · con Will Perez · "
                             "Llevar la llave: está en la bodega")
    assert summary(DIGEST).startswith("Reporte Karen, Orden de pedido · 2 facturas vencidas")
    assert heading("task_assigned", "[Alta] Tarea asignada: Revisar el riego") == "Revisar el riego"
    assert heading("daily_digest", "Tu día en TOMATO: 2 tareas") == "Tu día en TOMATO: 2 tareas"


def test_the_email_is_designed():
    html = email_html("task_assigned", "[Alta] Tarea asignada: Revisar el riego", TASK, "/dashboard/", "https://tomatocr.com")
    assert ">Tarea asignada</span>" in html and ">Revisar el riego</h1>" in html
    assert ">Tarea</td>" not in html  # the heading already says it
    assert ">Vence</td>" in html and "29/10/2026" in html and "#fee2e2;\">Alta</span>" in html
    assert 'href="https://tomatocr.com/dashboard/"' in html and "Ver mis tareas" in html
    assert "https://tomatocr.com/static/images/LogoTomatoW.png" in html and "/notificaciones" in html
    digest = email_html("daily_digest", "Tu día en TOMATO: 2 tareas", DIGEST, "/dashboard/", "https://tomatocr.com")
    assert ">Atrasada</span>" in digest and "Abrir el Dashboard" in digest


def test_the_text_is_escaped():
    html = email_html("new_lead", "Nueva oportunidad: <b>Hotel</b>", "Contacto: <script>x</script>", None, "https://tomatocr.com")
    assert "<script>x" not in html and "&lt;script&gt;" in html and "<b>Hotel" not in html


def test_a_task_email_goes_with_both_versions(db, login_as, users, outbox):
    users["worker"].email = "worker@example.com"
    db.commit()
    add_task(login_as("supervisor"), [users["worker"].id], title="Podar", priority="alta")
    mail = outbox[0]
    assert "Ver en el sistema: https://tomatocr.com/dashboard/" in mail["body"]  # plain text
    assert ">Podar</h1>" in mail["html"] and "Prioridad alta" in mail["html"]  # preheader


def test_the_bell_shows_label_and_summary(db, login_as, users):
    add_task(login_as("supervisor"), [users["worker"].id], title="Podar", description="Con tijera")
    page = login_as("worker").get("/notificaciones").text
    assert ">Tarea asignada</span>" in page and ">Podar</span>" in page
    assert "u_supervisor te asignó una tarea · Vence" in page and "bg-blue-100 text-blue-700" in page
