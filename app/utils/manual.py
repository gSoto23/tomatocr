"""User manual (/manual): one chapter per module, shown only to the roles that use it.
Each page's "?" button opens the chapter of its module (chapter_for_path).
Screenshots live in app/static/manual/<slug>/ and are regenerated with
scripts/manual/capturas.mjs from fictitious local data (never production)."""
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from app.core.roles import ADMIN, CLIENT, SUPERVISOR, VENTAS, WORKER

ALL_ROLES = (ADMIN, SUPERVISOR, WORKER, CLIENT, VENTAS)


@dataclass(frozen=True)
class Chapter:
    slug: str
    title: str
    summary: str
    roles: Tuple[str, ...]
    # URL prefixes whose "?" opens this chapter (longest match wins).
    paths: Tuple[str, ...] = ()
    # (anchor, title) of the sections, for the index and the search.
    sections: Tuple[Tuple[str, str], ...] = ()
    keywords: str = ""
    # Full-path regular expressions that win over prefixes (e.g. /projects/5/monitoreo).
    patterns: Tuple[str, ...] = ()

    def allowed(self, role: Optional[str]) -> bool:
        return role in self.roles


CHAPTERS: List[Chapter] = [
    Chapter(
        "primeros-pasos", "Primeros pasos",
        "Entrar al sistema, moverte por el menú y qué hacer si no podés ingresar.",
        ALL_ROLES, ("/cuenta",),
        (("entrar", "Entrar y salir"), ("contrasena", "Cambiar o recuperar la contraseña"), ("menu", "El menú"),
         ("ayuda", "Dónde encontrar ayuda"), ("problemas", "Si no podés entrar")),
        "login ingresar contraseña olvidé recuperar cambiar clave usuario sesión salir menú celular tablet",
    ),
    Chapter(
        "dashboard", "Dashboard",
        "La pantalla de inicio: lo más importante de tu día según tu rol.",
        ALL_ROLES, ("/dashboard",),
        (("que-es", "Qué es"), ("tareas", "Mis tareas"), ("alertas", "Alertas: Requiere atención"),
         ("por-rol", "Qué ves según tu rol"), ("preguntas", "Preguntas frecuentes")),
        "inicio resumen hoy tareas pendientes alertas ya lo vi prioridad facturas próximos pasos filtro bitácora",
    ),
    Chapter(
        "proyectos", "Proyectos y bitácora",
        "Los proyectos de jardinería y reforestación, y el registro diario del trabajo con fotos.",
        (ADMIN, SUPERVISOR, WORKER, CLIENT), ("/projects", "/logs"),
        (("que-es", "Qué es"), ("lista", "La lista de proyectos"), ("ficha", "La ficha del proyecto"),
         ("bitacora", "Registrar la bitácora del día"), ("reporte", "El reporte por correo al cliente"),
         ("crear", "Crear o editar un proyecto"), ("preguntas", "Preguntas frecuentes")),
        "proyecto bitácora registro diario fotos tareas horas reporte correo cliente contactos ubicación",
    ),
    Chapter(
        "calendario", "Calendario",
        "Quién trabaja en qué proyecto cada día y con qué tareas.",
        (ADMIN, SUPERVISOR, WORKER), ("/calendar",),
        (("que-es", "Qué es"), ("vistas", "Ver el calendario"), ("asignar", "Asignar un proyecto"),
         ("editar", "El día de un proyecto: personas, cambios y horas"), ("tareas", "Marcar las tareas hechas"), ("horas", "Las horas"),
         ("preguntas", "Preguntas frecuentes")),
        "calendario asignación asignar trabajador tareas día semana horas",
    ),
    Chapter(
        "planilla", "Planilla",
        "De las horas confirmadas al pago: aprobar horas, generar la planilla, pagos y liquidaciones.",
        (ADMIN, SUPERVISOR, WORKER), ("/payroll", "/payments", "/liquidation"),
        (("que-es", "Qué es"), ("ciclo", "El ciclo de cada planilla"), ("aprobar", "Confirmar las horas"),
         ("generar", "Generar y cerrar la planilla"), ("pagos", "Historial de pagos"), ("liquidacion", "Liquidaciones"),
         ("preguntas", "Preguntas frecuentes")),
        "planilla salario pago horas extra ccss deducciones vacaciones aguinaldo liquidación aprobar",
    ),
    Chapter(
        "clientes", "Clientes",
        "Cuentas y oportunidades: cómo trabajar una oportunidad hasta ganarla, y descartar lo que no sirve.",
        (ADMIN, VENTAS), ("/clientes",),
        (("que-es", "Qué es"), ("dia", "Tu día"), ("origen", "De dónde salen las oportunidades"),
         ("registrar", "Registrar una oportunidad"), ("etapas", "Las etapas"), ("descartar", "Descartar y borrar"),
         ("seguimientos", "Seguimientos"),
         ("cotizar", "Cotizar"), ("metas", "Qué cuenta para las metas"), ("permisos", "Qué podés ver y editar"),
         ("admin", "Tareas del admin"), ("datos", "Datos personales"), ("preguntas", "Preguntas frecuentes")),
        "crm cuentas prospectos oportunidades filtro embudo etapas metas piloto seguimientos vendedor asignación duplicados descartados descartar borrar spam",
    ),
    Chapter(
        "cotizador", "Cotizador",
        "Armar una cotización profesional, revisarla, exportarla en PDF y enviarla por correo.",
        (ADMIN, VENTAS, CLIENT), ("/cotizador",),
        (("que-es", "Qué es"), ("nueva", "Hacer una cotización"), ("revision", "La revisión antes del PDF"),
         ("pdf", "Exportar el PDF"), ("correo", "Enviar por correo"), ("guardadas", "Cotizaciones guardadas"),
         ("preguntas", "Preguntas frecuentes")),
        "cotización presupuesto pdf descuento iva ítems alcance términos número enviar correo adjunto",
    ),
]

CHAPTERS += [
    Chapter(
        "presupuestos", "Presupuestos",
        "Lo adjudicado, las facturas, los pagos que entran y los costos de cada proyecto.",
        (ADMIN, CLIENT), ("/finance",),
        (("que-es", "Qué es"), ("lista", "La lista de proyectos"),
         ("detalle", "El detalle financiero y qué significa cada número"), ("facturas", "Registrar una factura"),
         ("pagos", "Registrar un pago"), ("gastos", "Gastos del proyecto"), ("preguntas", "Preguntas frecuentes")),
        "presupuesto finanzas factura pago retención gasto costo saldo adjudicado facturado vencida",
    ),
    Chapter(
        "reforestacion", "Reforestación",
        "Inventario de árboles, monitoreos en campo, supervivencia y el mapa público.",
        (ADMIN, SUPERVISOR, WORKER), ("/dashboard/reforestacion",),
        (("que-es", "Qué es"), ("panel", "El panel de reforestación"), ("importar", "Cargar y actualizar el inventario (CSV)"),
         ("mapa", "El mapa público y la autorización del cliente"), ("monitoreo", "Registrar un monitoreo en campo"),
         ("corregir", "Corregir errores"), ("preguntas", "Preguntas frecuentes")),
        "reforestación árboles inventario csv monitoreo supervivencia mapa vivo muerto reemplazado borrar renombrar",
        patterns=(r"/projects/\d+/monitoreo",),
    ),
    Chapter(
        "empleados", "Empleados",
        "Crear y administrar a las personas que entran al sistema, sus datos de planilla y su expediente.",
        (ADMIN,), ("/users",),
        (("que-es", "Qué es"), ("lista", "La lista"), ("crear", "Crear o editar una persona"),
         ("contrasenas", "Contraseñas"), ("desactivar", "Desactivar o eliminar"), ("preguntas", "Preguntas frecuentes")),
        "empleados usuarios contraseña rol expediente documentos tarifa salario desactivar",
    ),
    Chapter(
        "actividad", "Actividad",
        "El registro de auditoría: quién hizo qué y cuándo.",
        (ADMIN,), ("/dashboard/activity",),
        (("que-es", "Qué es"), ("leer", "Leer el registro"), ("preguntas", "Preguntas frecuentes")),
        "actividad auditoría registro historial cambios login",
    ),
    Chapter(
        "recorridos", "Recorridos de punta a punta",
        "Cómo se conectan las partes del sistema en el trabajo de todos los días.",
        ALL_ROLES, (),
        (("prospecto-a-proyecto", "De una oportunidad a un proyecto ganado"),
         ("dia-de-trabajo", "Del día de trabajo al reporte del cliente"), ("renovacion", "Renovar un contrato")),
        "flujo proceso paso a paso de principio a fin",
    ),
]

BY_SLUG = {c.slug: c for c in CHAPTERS}


def chapters_for(role: Optional[str]) -> List[Chapter]:
    return [c for c in CHAPTERS if c.allowed(role)]


def chapter_for_path(path: str, role: Optional[str]) -> Optional[Chapter]:
    """Chapter that the "?" of this page opens, if the user can read it."""
    best, best_len = None, -1
    for chapter in chapters_for(role):
        if any(re.fullmatch(pattern, path) for pattern in chapter.patterns):
            return chapter
        for prefix in chapter.paths:
            if (path == prefix or path.startswith(prefix.rstrip("/") + "/")) and len(prefix) > best_len:
                best, best_len = chapter, len(prefix)
    return best


def help_url(path: str, role: Optional[str]) -> str:
    chapter = chapter_for_path(path, role)
    return f"/manual/{chapter.slug}" if chapter else "/manual"
