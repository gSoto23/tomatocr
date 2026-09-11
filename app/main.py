from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.db.base import Base
from app.db.session import engine
from app.routers import auth, projects, users, calendar, finance, dashboard, payroll, payments, liquidation, quotes, logs

app = FastAPI(title=settings.PROJECT_NAME)

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

# Mount static files
# Directory structure is app/static, so we mount it to /static path
app.mount("/static", StaticFiles(directory="app/static"), name="static")

from app.core.templates import templates

@app.get("/")
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/proyectos-reforestacion")
async def view_reforestation_report(request: Request):
    return templates.TemplateResponse("reforestacion.html", {"request": request})

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

from app.routers import reforestation
app.include_router(reforestation.router)
app.include_router(reforestation.public_router)

# Create tables on startup (Simple approach)
@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)

