
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from app.core.config import settings
from app.routers import auth
from app.db.base import Base
from app.db.session import engine
from app.db.models import user as user_model
from app.db.models import project as project_model
from app.routers import auth, deps, projects, logs, users
from fastapi import FastAPI, Request, Depends
from app.db.models.user import User

app = FastAPI(title=settings.PROJECT_NAME)

# Mount static files
# Directory structure is app/static, so we mount it to /static path
app.mount("/static", StaticFiles(directory="app/static"), name="static")

templates = Jinja2Templates(directory="app/templates")

@app.get("/")
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/dashboard")
async def dashboard(request: Request, user: User = Depends(deps.get_current_user)):
    return templates.TemplateResponse("dashboard.html", {"request": request, "user": user})

app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(logs.router)
app.include_router(users.router)

# Create tables on startup (Simple approach)
@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)

