
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

# Import models here for Alembic/create_all to find them
# from app.db.models.user import User  # This causes circular import if User imports Base
# Ideally, we import them in main or a separate 'models' init, but putting it here (bottom) or in main is key.
# from app.db.models.project import Project
from app.db.models.log import DailyLog, Photo
from app.db.models.schedule import ProjectSchedule
