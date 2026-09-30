import logging

from fastapi import Depends, FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse, PlainTextResponse, Response
from app.core.config import settings
from app.utils.servicios import SERVICIOS
from app.db.base import Base
from app.db.session import engine
from app.routers import auth, projects, users, calendar, finance, dashboard, payroll, payments, liquidation, quotes, logs

app = FastAPI(title=settings.PROJECT_NAME)
logger = logging.getLogger(__name__)

# CORS middleware configuration
# Antes era allow_origins=["*"] con allow_credentials=True — combinación
# insegura (permite que cualquier sitio haga solicitudes autenticadas usando
# la cookie de sesión del usuario). Todas las páginas de este sitio consumen
# su propia API en el mismo origen, así que no dependen de esta lista.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://tomatocr.com",
        "https://www.tomatocr.com",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Redirect www.tomatocr.com to the canonical apex domain (avoids duplicate-content indexing)
@app.middleware("http")
async def redirect_www_to_apex(request: Request, call_next):
    host = request.headers.get("host", "")
    if host.startswith("www."):
        target = request.url.replace(netloc=host[len("www."):])
        return RedirectResponse(url=str(target), status_code=308)
    return await call_next(request)


# Public pages reached with a trailing slash redirect for good (308) instead of FastAPI's
# temporary 307, so search engines keep a single URL. Internal routes keep their own slashes.
PUBLIC_SLASH_PATHS = {"/proyectos-reforestacion/", "/programas/darboles/", "/privacidad/", "/contacto/gracias/",
                      *(f"/servicios/{slug}/" for slug in SERVICIOS)}
STATIC_VERSIONED = "public, max-age=31536000, immutable"  # CSS/JS carry ?v=<mtime>
STATIC_PLAIN = "public, max-age=604800"                   # images: 7 days; a changed image gets a new name


@app.middleware("http")
async def seo_and_cache_headers(request: Request, call_next):
    path = request.url.path
    if request.method in ("GET", "HEAD") and path in PUBLIC_SLASH_PATHS:
        target = request.url.replace(path=path.rstrip("/"))
        return RedirectResponse(url=str(target), status_code=308)
    response = await call_next(request)
    response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
    if path.startswith("/static/") and response.status_code == 200:
        response.headers["Cache-Control"] = STATIC_VERSIONED if "v=" in request.url.query else STATIC_PLAIN
    return response

# Mount static files
# Directory structure is app/static, so we mount it to /static path
app.mount("/static", StaticFiles(directory="app/static"), name="static")

from app.core.templates import templates
from app.routers import deps
from app.utils.reforestation import public_stats

def safe_public_stats(db: Session):
    """The live figures are a bonus: if the query fails, the page still loads without them."""
    try:
        return public_stats(db)
    except SQLAlchemyError:
        logger.exception("Public reforestation figures unavailable")
        db.rollback()
        return None


@app.api_route("/", methods=["GET", "HEAD"])
def read_root(request: Request, db: Session = Depends(deps.get_db)):
    return templates.TemplateResponse("index.html", {"request": request, "stats": safe_public_stats(db)})

@app.api_route("/proyectos-reforestacion", methods=["GET", "HEAD"])
def view_reforestation_report(request: Request, db: Session = Depends(deps.get_db)):
    # Figures rendered on the server too, so search engines read them without running the map's JavaScript.
    return templates.TemplateResponse("reforestacion.html", {"request": request, "stats": safe_public_stats(db)})

@app.api_route("/servicios/{slug}", methods=["GET", "HEAD"])
def view_service(slug: str, request: Request, db: Session = Depends(deps.get_db)):
    service = SERVICIOS.get(slug)
    if not service:
        raise StarletteHTTPException(status_code=404)
    stats = safe_public_stats(db) if service.get("live_stats") else None
    faq_ld = [{"@type": "Question", "name": question, "acceptedAnswer": {"@type": "Answer", "text": answer}}
              for question, answer in service["faq"]]
    return templates.TemplateResponse("servicios/servicio.html", {
        "request": request, "slug": slug, "s": service, "servicios": SERVICIOS, "stats": stats, "faq_ld": faq_ld})

@app.api_route("/programas/darboles", methods=["GET", "HEAD"])
async def view_darboles_program(request: Request):
    return templates.TemplateResponse("programas/darboles.html", {"request": request})

PUBLIC_PAGES = ["", *(f"servicios/{slug}" for slug in SERVICIOS), "proyectos-reforestacion", "programas/darboles",
                "privacidad"]

@app.get("/robots.txt", response_class=PlainTextResponse)
async def robots_txt():
    return "User-agent: *\nAllow: /\n\nSitemap: https://tomatocr.com/sitemap.xml\n"

@app.get("/sitemap.xml")
async def sitemap_xml():
    urls = "\n".join(
        f"  <url><loc>https://tomatocr.com/{path}</loc></url>" for path in PUBLIC_PAGES
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{urls}\n"
        "</urlset>\n"
    )
    return Response(content=xml, media_type="application/xml")

# Pages opened in the browser get a Spanish error page instead of raw JSON; fetch/API
# calls (and anything that isn't a GET for HTML) keep the JSON they expect.
from fastapi.exception_handlers import http_exception_handler  # noqa: E402
from starlette.exceptions import HTTPException as StarletteHTTPException  # noqa: E402

ERROR_TITLES = {403: "No tenés acceso a esta página", 404: "No encontramos lo que buscás",
                400: "No se pudo completar", 405: "Esa acción no está disponible"}
ENGLISH_DETAILS = ("not authorized", "forbidden", "not found", "method not allowed", "invalid")


def wants_html(request: Request) -> bool:
    return (request.method in ("GET", "HEAD") and not request.url.path.startswith("/api/")
            and "text/html" in request.headers.get("accept", ""))


@app.exception_handler(StarletteHTTPException)
async def friendly_http_errors(request: Request, exc: StarletteHTTPException):
    if not wants_html(request) or exc.status_code < 400 or exc.status_code == 401:
        return await http_exception_handler(request, exc)
    detail = str(exc.detail or "")
    if not detail or any(word in detail.lower() for word in ENGLISH_DETAILS):
        detail = {403: "Tu usuario no tiene permiso para ver esto. Si lo necesitás, pedíselo al admin.",
                  404: "La página o el registro no existe, o fue borrado."}.get(
            exc.status_code, "Algo no salió bien. Volvé atrás e intentá de nuevo.")
    return templates.TemplateResponse("errors/page.html", {
        "request": request, "status_code": exc.status_code, "message": detail,
        "title": ERROR_TITLES.get(exc.status_code, "Algo no salió bien"),
    }, status_code=exc.status_code)


app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(projects.router)
app.include_router(users.router)
app.include_router(calendar.router)
app.include_router(finance.router)
app.include_router(payroll.router)
app.include_router(payments.router)
app.include_router(liquidation.router)
app.include_router(quotes.router)
app.include_router(logs.router)

from app.routers import reforestation, crm, leads, manual, account, darboles_sync
app.include_router(reforestation.router)
app.include_router(reforestation.public_router)
app.include_router(crm.router)
app.include_router(leads.router)
app.include_router(darboles_sync.router)
app.include_router(manual.router)
app.include_router(account.router)

# SQLite (local dev, and prod until it moves to PostgreSQL) still creates its
# tables on startup. On PostgreSQL the schema is managed only by Alembic.
@app.on_event("startup")
def on_startup():
    if settings.USE_SQLITE:
        Base.metadata.create_all(bind=engine)

