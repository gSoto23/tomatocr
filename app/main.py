
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from app.core.config import settings
from app.routers import auth
from app.db.base import Base
from app.db.session import engine
from app.db.models import user as user_model
from app.db.models import project as project_model
from app.routers import auth, deps, projects, logs, users, calendar, finance, dashboard
from fastapi import FastAPI, Request, Depends
from app.db.models.user import User

app = FastAPI(title=settings.PROJECT_NAME)

# Mount static files
# Directory structure is app/static, so we mount it to /static path
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.mount("/cotizador", StaticFiles(directory="app/cotizador", html=True), name="cotizador")

from app.core.templates import templates

@app.get("/")
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(projects.router)
app.include_router(logs.router)
app.include_router(users.router)
app.include_router(calendar.router)
app.include_router(finance.router)

# Create tables on startup (Simple approach)
@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)

