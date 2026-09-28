"""User manual (/manual): one chapter per module, shown only to the roles that use it.
Each page's "?" button opens the chapter of its module (chapter_for_path).
Screenshots live in app/static/manual/<slug>/ and are regenerated with
scripts/manual/capturas.mjs from fictitious local data (never production)."""
from dataclasses import dataclass, field
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

    def allowed(self, role: Optional[str]) -> bool:
        return role in self.roles


CHAPTERS: List[Chapter] = [
    Chapter(
        "primeros-pasos", "Primeros pasos",
        "Entrar al sistema, moverte por el menú y qué hacer si no podés ingresar.",
        ALL_ROLES, (),
        (("entrar", "Entrar y salir"), ("menu", "El menú"), ("ayuda", "Dónde encontrar ayuda"),
         ("problemas", "Si no podés entrar")),
        "login ingresar contraseña usuario sesión salir menú celular tablet",
    ),
    Chapter(
        "dashboard", "Dashboard",
        "La pantalla de inicio: lo más importante de tu día según tu rol.",
        ALL_ROLES, ("/dashboard",),
        (("que-es", "Qué es"), ("por-rol", "Qué ves según tu rol"), ("preguntas", "Preguntas frecuentes")),
        "inicio resumen facturas pendientes próximos pasos embudo bitácora",
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
        "clientes", "Clientes",
        "Cuentas, prospectos y oportunidades: cómo trabajar un prospecto hasta ganarlo.",
        (ADMIN, VENTAS), ("/clientes",),
        (("que-es", "Qué es"), ("dia", "Tu día"), ("origen", "De dónde salen los prospectos"),
         ("registrar", "Registrar un prospecto"), ("etapas", "Las etapas"), ("seguimientos", "Seguimientos"),
         ("cotizar", "Cotizar"), ("metas", "Qué cuenta para las metas"), ("permisos", "Qué podés ver y editar"),
         ("admin", "Tareas del admin"), ("datos", "Datos personales"), ("preguntas", "Preguntas frecuentes")),
        "crm cuentas prospectos oportunidades embudo etapas metas piloto seguimientos vendedor asignación duplicados",
    ),
    Chapter(
        "cotizador", "Cotizador",
        "Armar una cotización profesional, revisarla y exportarla en PDF.",
        (ADMIN, VENTAS, CLIENT), ("/cotizador",),
        (("que-es", "Qué es"), ("nueva", "Hacer una cotización"), ("revision", "La revisión antes del PDF"),
         ("pdf", "Exportar el PDF"), ("guardadas", "Cotizaciones guardadas"), ("preguntas", "Preguntas frecuentes")),
        "cotización presupuesto pdf descuento iva ítems alcance términos número",
    ),
]

BY_SLUG = {c.slug: c for c in CHAPTERS}


def chapters_for(role: Optional[str]) -> List[Chapter]:
    return [c for c in CHAPTERS if c.allowed(role)]


def chapter_for_path(path: str, role: Optional[str]) -> Optional[Chapter]:
    """Chapter that the "?" of this page opens, if the user can read it."""
    best, best_len = None, -1
    for chapter in chapters_for(role):
        for prefix in chapter.paths:
            if (path == prefix or path.startswith(prefix.rstrip("/") + "/")) and len(prefix) > best_len:
                best, best_len = chapter, len(prefix)
    return best


def help_url(path: str, role: Optional[str]) -> str:
    chapter = chapter_for_path(path, role)
    return f"/manual/{chapter.slug}" if chapter else "/manual"
