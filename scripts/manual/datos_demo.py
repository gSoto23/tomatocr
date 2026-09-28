"""Fictitious data for the user manual screenshots (scripts/manual/README.md).

Creates (or recreates) the LOCAL PostgreSQL database `tomato_manual`, applies the
migrations and fills it with invented companies, people, projects, reports,
opportunities and quotes. It refuses to run against anything but a local server,
so production data never ends up in a screenshot.

    DB_SERVER=127.0.0.1 DB_PORT=55432 DB_USER=tomato DB_PASSWORD=... SECRET_KEY=... \\
        USE_SQLITE=False PYTHONPATH=. python scripts/manual/datos_demo.py
"""
import os
import secrets
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

DEMO_DB = "tomato_manual"
# role -> (username, full name). The users only exist in the demo database.
DEMO_USERS = {
    "admin": ("manual_admin", "Laura Méndez"),
    "ventas": ("manual_ventas", "Diego Rojas"),
    "supervisor": ("manual_supervisor", "Carlos Vargas"),
    "worker": ("manual_trabajador", "Andrés Solano"),
    "client": ("manual_cliente", "Sofía Castro"),
}
ROOT = Path(__file__).resolve().parents[2]
PHOTOS = ROOT / "app" / "static" / "uploads" / "manual-demo"


def check_local():
    host = os.environ.get("DB_SERVER", "")
    if host not in ("127.0.0.1", "localhost", "::1"):
        sys.exit(f"datos_demo.py solo corre contra una base local (DB_SERVER={host!r}).")
    if os.environ.get("USE_SQLITE", "").lower() in ("1", "true", "yes"):
        sys.exit("Use PostgreSQL local: USE_SQLITE=False.")
    os.environ["DB_NAME"] = DEMO_DB


def recreate_database():
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import URL
    url = URL.create("postgresql", username=os.environ["DB_USER"], password=os.environ.get("DB_PASSWORD"),
                     host=os.environ["DB_SERVER"], port=int(os.environ.get("DB_PORT") or 5432), database="postgres")
    engine = create_engine(url, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {DEMO_DB} WITH (FORCE)"))
        conn.execute(text(f"CREATE DATABASE {DEMO_DB}"))
    engine.dispose()
    subprocess.run([str(ROOT / ".venv" / "bin" / "alembic"), "upgrade", "head"], cwd=ROOT, check=True,
                   env={**os.environ, "DB_NAME": DEMO_DB}, stdout=subprocess.DEVNULL)


def demo_photo(name: str, color: tuple, label: str) -> str:
    """A plain placeholder image, so no real photo is ever used."""
    from PIL import Image, ImageDraw, ImageFont
    PHOTOS.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (1200, 900), color)
    draw = ImageDraw.Draw(image)
    for i in range(0, 900, 60):
        draw.line([(0, i), (1200, i + 200)], fill=tuple(min(255, c + 18) for c in color), width=18)
    draw.rectangle([230, 380, 970, 520], fill=(255, 255, 255))
    draw.text((600, 450), f"Foto de ejemplo · {label}", fill=(40, 40, 40), anchor="mm",
              font=ImageFont.load_default(size=44))
    image.save(PHOTOS / name, "JPEG", quality=80)
    return f"/static/uploads/manual-demo/{name}"


def fill():
    import app.db.base  # noqa: F401  (registers every model)
    from app.core.security import pwd_context
    from app.db.models.activity import ActivityLog
    from app.db.models.crm import (Account, Contact, CrmActivity, CrmAssignment, CrmSetting, Opportunity,
                                   ProjectContactRole, stage_index)
    from app.db.models.finance import BudgetLine, Invoice, InvoiceStatus, Payment, ProjectBudget, ProjectCost
    from app.db.models.payment import PayrollPayment
    from app.db.models.payroll import PayrollEntry, PayrollPeriod
    from app.db.models.reforestation import ReforestationProject, ReforestationTree, TreeCheck
    from app.db.models.log import DailyLog, Photo
    from app.db.models.log_task import DailyLogTask
    from app.db.models.project import Project
    from app.db.models.project_details import ProjectLocation, ProjectSupply, ProjectTask
    from app.db.models.quote import Quote
    from app.db.models.schedule import ProjectSchedule, ScheduleTask
    from app.db.models.user import User
    from app.db.session import SessionLocal

    today = date.today()
    now = datetime.utcnow()
    db = SessionLocal()
    password = pwd_context.hash(secrets.token_urlsafe(24), rounds=4)
    users = {}
    for role, (username, full_name) in DEMO_USERS.items():
        users[role] = User(username=username, hashed_password=password, full_name=full_name, role=role,
                           is_active=True, status="active", email=f"{username}@example.com", hourly_rate=2500)
    extra_worker = User(username="manual_trabajador2", hashed_password=password, full_name="María Jiménez",
                        role="worker", is_active=True, status="active", hourly_rate=2500)
    db.add_all([*users.values(), extra_worker])
    db.flush()
    admin, ventas = users["admin"], users["ventas"]

    # --- Clientes ------------------------------------------------------------------------
    def account(name, kind="empresa", owner=ventas, **fields):
        a = Account(name=name, kind=kind, owner_id=owner.id if owner else None, created_at=now - timedelta(days=20),
                    **fields)
        db.add(a)
        db.flush()
        return a

    def contact(acc, name, email=None, phone=None, role_title=None, primary=True, **fields):
        c = Contact(account_id=acc.id, name=name, email=email, phone=phone, role_title=role_title,
                    is_primary=primary, is_commercial=True, **fields)
        db.add(c)
        db.flush()
        return c

    robles = account("Condominio Los Robles", "condominio", owner=admin, province="Heredia",
                     tax_id="3-109-000001")
    sofia = contact(robles, "Sofía Castro", "sofia.castro@example.com", "8800-1001", "Administradora",
                    user_id=users["client"].id)
    jorge = contact(robles, "Jorge Arias", "jorge.arias@example.com", "8800-1002", "Presidente de la junta",
                    primary=False)
    sabana = account("Oficentro La Sabana", owner=admin, province="San José")
    contact(sabana, "Patricia Vega", "patricia.vega@example.com", "8800-2001", "Gerente de mantenimiento")
    hotel = account("Hotel Vista al Volcán", "hotel", province="Alajuela")
    contact(hotel, "Ricardo Solís", "ricardo.solis@example.com", "8800-3001", "Gerente general")
    banco = account("Banco del Valle", province="San José")
    contact(banco, "Mariana Quesada", "mariana.quesada@example.com", "8800-4001", "Jefa de sostenibilidad")
    muni = account("Municipalidad de San Rafael", "institucion_publica", owner=admin, province="Heredia")
    contact(muni, "Esteban Mora", "esteban.mora@example.com", "2260-0000", "Gestión ambiental")
    cafe = account("Café Montaña Alta", province="Cartago")
    contact(cafe, "Lucía Brenes", "lucia.brenes@example.com", "8800-5001", "Mercadeo")
    colegio = account("Colegio Bilingüe Arenal", province="Guanacaste")
    contact(colegio, "Andrea Campos", "andrea.campos@example.com", None, "Directora")
    account("Colegio Bilingue Arenal S.A.", owner=None, province="Guanacaste")  # a likely duplicate

    def opp(acc, title, motor, stage, owner=ventas, step=None, step_days=None, days_ago=10, kind="nuevo", **fields):
        o = Opportunity(account_id=acc.id, title=title, motor=motor, stage=stage, kind=kind,
                        max_stage=stage_index(stage) if stage != "perdido" else fields.pop("max_stage", 1),
                        owner_id=owner.id, next_step=step,
                        next_step_date=today + timedelta(days=step_days) if step_days is not None else None,
                        created_at=now - timedelta(days=days_ago), source=fields.pop("source", "linkedin"), **fields)
        db.add(o)
        db.flush()
        return o

    o_hotel = opp(hotel, "Jardines y áreas verdes del hotel", "mantenimiento", "reunion", step="Enviar propuesta",
                  step_days=-2, days_ago=12, amount_crc=1850000)
    o_banco = opp(banco, "Reforestación con colaboradores", "esg", "propuesta", step="Llamar para confirmar",
                  step_days=0, days_ago=15, amount_crc=4200000)
    opp(cafe, "Regalo corporativo de fin de año", "regalo_corporativo", "respuesta", step="Coordinar reunión",
        step_days=3, days_ago=6, source="web")
    opp(muni, "Arborización de parques", "sector_publico", "prospecto", owner=admin, step="Revisar cartel en SICOP",
        step_days=5, days_ago=4, source="sicop")
    opp(colegio, "Mantenimiento de canchas", "mantenimiento", "perdido", step=None, days_ago=9,
        lost_reason="Eligieron un proveedor más cercano", max_stage=stage_index("respuesta"))
    for o, notes in ((o_hotel, "Visita al hotel: 3 hectáreas de jardín, quieren propuesta mensual."),
                     (o_banco, "Enviada la cotización TCR-2026-0102 para 500 árboles.")):
        db.add(CrmActivity(account_id=o.account_id, opportunity_id=o.id, type="reunion",
                           happened_at=now - timedelta(days=3), notes=notes, user_id=ventas.id))
    period_start, period_end = today - timedelta(days=30), today + timedelta(days=45)
    for key, value in (("funnel_name", "Piloto"), ("funnel_start", period_start.isoformat()),
                       ("funnel_end", period_end.isoformat())):
        row = db.get(CrmSetting, key) or CrmSetting(key=key)
        row.value = value
        db.add(row)
    for motor in ("esg", "regalo_corporativo", "mantenimiento", "tienda"):
        row = db.get(CrmAssignment, motor) or CrmAssignment(motor=motor)
        row.user_id = ventas.id
        db.add(row)
    for motor in ("sector_publico", "_default"):
        row = db.get(CrmAssignment, motor) or CrmAssignment(motor=motor)
        row.user_id = admin.id
        db.add(row)

    # --- Proyectos -----------------------------------------------------------------------
    p1 = Project(name="Mantenimiento Condominio Los Robles", client_display_name=robles.name, account_id=robles.id,
                 province="Heredia", address="Del parque central 300 m norte, San Pablo",
                 waze_link="https://waze.com/ul?ll=10.0,-84.1", is_active=True,
                 description="Mantenimiento mensual de zonas verdes comunes, jardineras de las torres y área de juegos.")
    p1.users = [users["client"], users["worker"], users["supervisor"], extra_worker]
    p2 = Project(name="Zonas verdes Oficentro La Sabana", client_display_name=sabana.name, account_id=sabana.id,
                 province="San José", address="Sabana Norte", is_active=True)
    p2.users = [users["worker"], users["supervisor"]]
    p3 = Project(name="Reforestación Cuenca Río Segundo", client_display_name=muni.name, account_id=muni.id,
                 province="Heredia", address="Margen del río, San Rafael", is_active=True)
    p3.users = [users["supervisor"]]
    p4 = Project(name="Jardín Casa Escazú", client_display_name="Familia Rodríguez", province="San José",
                 is_active=False)
    db.add_all([p1, p2, p3, p4])
    db.flush()
    tasks = [ProjectTask(project_id=p1.id, description=d, is_required=r) for d, r in (
        ("Corta de zacate en áreas comunes", True), ("Poda de setos y arbustos", False),
        ("Limpieza de jardineras", True), ("Riego de plantas ornamentales", False))]
    torres = [ProjectLocation(project_id=p1.id, name="Torre A", location="Entrada principal"),
              ProjectLocation(project_id=p1.id, name="Torre B", location="Costado sur")]
    db.add_all(tasks + torres + [ProjectSupply(project_id=p1.id, name="Abono orgánico", quantity="2 sacos"),
                                 ProjectSupply(project_id=p1.id, name="Hilo para desbrozadora", quantity="1 rollo"),
                                 ProjectTask(project_id=p2.id, description="Corta de zacate", is_required=True)])
    db.flush()
    db.add_all([ProjectContactRole(project_id=p1.id, contact_id=sofia.id, is_site=True, receives_reports=True),
                ProjectContactRole(project_id=p1.id, contact_id=jorge.id, is_site=False, receives_reports=True)])
    budget = ProjectBudget(project_id=p1.id, licitation_number="CONT-2026-014", contract_duration="12 meses",
                           start_date=today - timedelta(days=120), end_date=today + timedelta(days=245),
                           is_prorrogable=True, prorrogable_time="12 meses", prorrogable_amount=0)
    db.add(budget)
    db.flush()
    line = BudgetLine(budget_id=budget.id, name="Mantenimiento mensual de zonas verdes (12 meses)", subtotal=11400000,
                      tax_percentage=13)
    line2 = BudgetLine(budget_id=budget.id, name="Resiembra de jardineras", subtotal=380000, tax_percentage=13)
    db.add_all([line, line2])
    db.flush()
    invoices = [
        Invoice(budget_id=budget.id, budget_line_id=line.id, invoice_number="FE-00121", amount=1073500,
                issue_date=today - timedelta(days=62), due_date=today - timedelta(days=32), status=InvoiceStatus.PAID),
        Invoice(budget_id=budget.id, budget_line_id=line.id, invoice_number="FE-00134", amount=1073500,
                issue_date=today - timedelta(days=35), due_date=today - timedelta(days=5),
                status=InvoiceStatus.OVERDUE),
        Invoice(budget_id=budget.id, budget_line_id=line.id, invoice_number="FE-00147", amount=1073500,
                issue_date=today - timedelta(days=4), due_date=today + timedelta(days=26),
                status=InvoiceStatus.PENDING),
        Invoice(budget_id=budget.id, budget_line_id=line2.id, invoice_number="FE-00148", amount=429400,
                issue_date=today - timedelta(days=4), due_date=today + timedelta(days=26),
                status=InvoiceStatus.PARTIAL),
    ]
    db.add_all(invoices)
    db.flush()
    db.add(Payment(invoice_id=invoices[0].id, payment_date=today - timedelta(days=30), amount=1073500,
                   deposit_number="TRF-88321"))

    notes = [
        "Se cortó el zacate en todas las áreas comunes y se limpiaron las jardineras de la entrada. "
        "Se recomienda revisar el riego automático de la Torre B.",
        "Poda de setos en el perímetro y limpieza de jardineras. Se retiraron dos sacos de hojas.",
        "Corta de zacate y riego de plantas ornamentales. El área de juegos quedó lista.",
    ]
    colors = [(64, 120, 70), (80, 135, 60), (55, 105, 85)]
    for i, text in enumerate(notes):
        log = DailyLog(project_id=p1.id, user_id=users["worker"].id, date=today - timedelta(days=7 * i),
                       notes=text, location_id=torres[i % 2].id)
        db.add(log)
        db.flush()
        for t in (tasks[0], tasks[2], tasks[1] if i == 1 else tasks[3]):
            db.add(DailyLogTask(log_id=log.id, task_id=t.id, completed=True))
        for k in range(2 if i else 3):
            db.add(Photo(log_id=log.id, file_path=demo_photo(f"reporte{i + 1}-{k + 1}.jpg", colors[(i + k) % 3],
                                                             f"reporte {i + 1}")))

    for days, worker, loc in ((0, users["worker"], torres[0]), (1, users["worker"], torres[1]),
                              (3, users["worker"], torres[0]), (0, extra_worker, torres[1])):
        schedule = ProjectSchedule(project_id=p1.id, user_id=worker.id, location_id=loc.id,
                                   date=today + timedelta(days=days), hours_worked=8)
        db.add(schedule)
        db.flush()
        db.add_all([ScheduleTask(schedule_id=schedule.id, description="Corta de zacate", completed=days == 0),
                    ScheduleTask(schedule_id=schedule.id, description="Limpieza de jardineras")])
    schedule = ProjectSchedule(project_id=p2.id, user_id=users["worker"].id, date=today + timedelta(days=2))
    db.add(schedule)
    db.flush()
    db.add(ScheduleTask(schedule_id=schedule.id, description="Corta de zacate"))

    # --- Planilla ---------------------------------------------------------------------------
    worker, maria, supervisor = users["worker"], extra_worker, users["supervisor"]
    for person, start, salary, method, account_no in (
            (worker, date(2025, 3, 3), 441600, "Sinpe", "8800-7001"), (maria, date(2025, 11, 3), 441600, "Efectivo", None),
            (supervisor, date(2024, 8, 1), 576000, "Transferencia", "CR05015201001026284066")):
        person.start_date, person.monthly_salary, person.hourly_rate = start, salary, round(salary / 192 / 100) * 100
        person.payment_method, person.account_number, person.phone = method, account_no, "8800-9000"
    p3.users = [users["supervisor"], worker]

    def weekdays(first, last):
        day = first
        while day <= last:
            if day.weekday() < 5:
                yield day
            day += timedelta(days=1)

    confirmed = []
    for day in weekdays(today - timedelta(days=28), today - timedelta(days=1)):
        for person, project, extra in ((worker, p1, 1.0 if day.weekday() == 4 else 0.0), (maria, p2, 0.0),
                                       (supervisor, p1, 0.0)):
            schedule = ProjectSchedule(project_id=project.id, user_id=person.id, date=day, hours_worked=8,
                                       overtime_hours=extra, is_confirmed=True)
            db.add(schedule)
            confirmed.append(schedule)
    db.flush()

    def payroll(first, last, status):
        period = PayrollPeriod(start_date=first, end_date=last, status=status)
        db.add(period)
        db.flush()
        for person in (worker, maria, supervisor):
            rows = [s for s in confirmed if s.user_id == person.id and first <= s.date <= last]
            hours, extra = sum(s.hours_worked for s in rows), sum(s.overtime_hours for s in rows)
            gross = round((hours * person.hourly_rate + extra * person.hourly_rate * 1.5) / 100) * 100
            charges = round(gross * 0.0917 / 100) * 100
            db.add(PayrollEntry(payroll_period_id=period.id, user_id=person.id, total_hours=hours, overtime_hours=extra,
                                gross_salary=gross, social_charges=charges, net_salary=gross - charges,
                                apply_deductions=True,
                                details=[{"date": s.date.isoformat(), "hours": s.hours_worked,
                                          "overtime": s.overtime_hours,
                                          "project": p1.name if s.project_id == p1.id else p2.name} for s in rows]))
        return period
    payroll(today - timedelta(days=28), today - timedelta(days=15), "final")
    payroll(today - timedelta(days=14), today - timedelta(days=1), "draft")
    db.add_all([PayrollPayment(user_id=worker.id, amount=172400, hours_paid=80, overtime_hours=2,
                               date=today - timedelta(days=13), notes="Quincena por Sinpe", created_by_id=admin.id),
                PayrollPayment(user_id=maria.id, amount=167000, hours_paid=80, date=today - timedelta(days=13),
                               notes="Quincena en efectivo", created_by_id=admin.id)])
    db.add_all([ProjectCost(project_id=p1.id, date=today - timedelta(days=20), amount=48500,
                            description="Abono orgánico y sustrato"),
                ProjectCost(project_id=p1.id, date=today - timedelta(days=9), amount=22000,
                            description="Transporte de residuos verdes")])

    # --- Reforestación ------------------------------------------------------------------------
    forest = ReforestationProject(client_name="Municipalidad de San Rafael", project_id=p3.id, account_id=muni.id,
                                  is_public=True, public_name="Municipalidad de San Rafael",
                                  consent_date=today - timedelta(days=60))
    db.add(forest)
    db.flush()
    species = ["Guanacaste", "Cortez amarillo", "Roble sabana", "Cenízaro", "Poró", "Guachipelín"]
    sectors = [("Margen norte", 10.0258, -84.0995), ("Margen sur", 10.0231, -84.0972), ("Parque lineal", 10.0209, -84.1021)]
    planted = today.replace(year=today.year - 1) - timedelta(days=30)
    trees = []
    for n in range(1, 43):
        name, lat, lng = sectors[(n - 1) // 14]
        tree = ReforestationTree(project_id=forest.id, tree_number=n, species=species[n % len(species)],
                                 sector_name=name, lat=lat + (n % 7) * 0.0004, lng=lng + (n % 5) * 0.0005,
                                 date_planted=planted if n <= 36 else today - timedelta(days=90))
        db.add(tree)
        trees.append(tree)
    db.flush()
    check_day = today - timedelta(days=10)
    for tree in trees[:30]:
        status = "muerto" if tree.tree_number in (4, 11, 19) else "reemplazado" if tree.tree_number == 23 else "vivo"
        tree.status, tree.last_checked_at = status, check_day
        db.add(TreeCheck(tree_id=tree.id, checked_at=check_day, status=status, user_id=supervisor.id,
                         height_cm=90 + tree.tree_number * 3 if status == "vivo" else None))
    trees[22].replaced_by_id = trees[41].id

    for action, entity, details, who in (
            ("LOGIN", "SISTEMA", "Inicio de sesión", worker), ("CREATE", "REPORT", "Reporte del proyecto Mantenimiento Condominio Los Robles", worker),
            ("EMAIL", "REPORT", "Reporte enviado a sofia.castro@example.com, jorge.arias@example.com", admin),
            ("PAGO", "Factura", "Pago registrado para la factura FE-00121", admin),
            ("Aprobar Lote", "SCHEDULE", "10 registros confirmados en Mantenimiento Condominio Los Robles", supervisor),
            ("Generar Planilla", "PAYROLL", "Periodo del último mes", admin)):
        db.add(ActivityLog(user_id=who.id, action=action, entity_type=entity, details=details))

    # --- Cotizaciones ----------------------------------------------------------------------
    year = today.year
    items = [{"id": "1", "type": "Servicio", "description": "Mantenimiento mensual de jardines (4 visitas)",
              "unit": "Mes", "qty": 1, "unitPrice": 850000},
             {"id": "2", "type": "Material", "description": "Abono orgánico", "unit": "Saco", "qty": 4,
              "unitPrice": 12500}]
    for number, acc, name, total, opportunity, days in (
            (f"TCR-{year}-0101", hotel, hotel.name, 1017000, o_hotel, 5),
            (f"TCR-{year}-0102", banco, banco.name, 4746000, o_banco, 3),
            (f"TCR-{year}-0103", robles, robles.name, 1073500, None, 1)):
        db.add(Quote(numero_cotizacion=number, fecha_emision=today - timedelta(days=days), cliente_nombre=name,
                     cliente_datos={"name": name}, moneda="CRC", tipo_servicio="Jardinería", frecuencia="Mensual",
                     validez_dias=15, notes="Incluye mano de obra, herramientas y retiro de residuos.",
                     terminos="1. Validez: 15 días.\n2. Incluye mano de obra.", subtotal=round(total / 1.13),
                     iva=total - round(total / 1.13), total=total, tax_rate=13, items=items, account_id=acc.id,
                     opportunity_id=opportunity.id if opportunity else None))
    db.add(ActivityLog(user_id=admin.id, action="IMPORT", entity_type="MANUAL", details="Datos de ejemplo del manual"))
    db.commit()
    db.close()


if __name__ == "__main__":
    check_local()
    recreate_database()
    fill()
    print(f"Base {DEMO_DB} lista con datos de ejemplo. Usuarios: "
          + ", ".join(f"{role}={username}" for role, (username, _) in DEMO_USERS.items()))
