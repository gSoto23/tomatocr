
import sys
import os
import asyncio
import json
from datetime import datetime, date, timedelta
from sqlalchemy.orm import Session

from app.main import app
from app.db.session import SessionLocal
from app.db.models.user import User
from app.db.models.project import Project
from app.db.models.schedule import ProjectSchedule
from app.routers.calendar import create_schedule

async def run_verification():
    db = SessionLocal()
    
    # Prerequisite: active project and worker
    project = db.query(Project).filter(Project.is_active == True).first()
    worker = db.query(User).filter(User.role == "worker").first() # or any user
    admin = db.query(User).filter(User.role == "admin").first()
    if not admin:
        admin = db.query(User).filter(User.role == "supervisor").first()
    
    if not project or not worker or not admin:
        print("Missing prerequisites: Project, Worker or Admin not found.")
        return

    print(f"Using Project: {project.name} (ID: {project.id})")
    print(f"Using Worker: {worker.username} (ID: {worker.id})")
    print(f"Using Admin: {admin.username} (ID: {admin.id})")

    # Clean up any existing schedules for this test range
    start_date_str = "2026-05-01"
    end_date_str = "2026-05-03" # 3 days: 01, 02, 03
    
    start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
    end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
    
    db.query(ProjectSchedule).filter(
        ProjectSchedule.user_id == worker.id,
        ProjectSchedule.project_id == project.id,
        ProjectSchedule.date >= start_date,
        ProjectSchedule.date <= end_date
    ).delete()
    db.commit()

    # Test Function Call
    try:
        response = await create_schedule(
            project_id=project.id,
            user_id=worker.id,
            date_val=start_date_str,
            end_date=end_date_str,
            tasks_json="[]",
            db=db,
            user=admin
        )
        # response is a JSONResponse object
        import json
        body = json.loads(response.body)
        print(f"Response: {body}")
        
        if response.status_code != 200:
             print(f"FAIL: Status code {response.status_code}")
             return

    except Exception as e:
        print(f"FAIL: Exception occurred: {e}")
        import traceback
        traceback.print_exc()
        return

    # Verify Logic
    schedules = db.query(ProjectSchedule).filter(
        ProjectSchedule.user_id == worker.id,
        ProjectSchedule.project_id == project.id,
        ProjectSchedule.date >= start_date,
        ProjectSchedule.date <= end_date
    ).all()
    
    print(f"Found {len(schedules)} schedules created.")
    
    expected_count = 3
    if len(schedules) == expected_count:
        print("SUCCESS: 3 schedules created as expected.")
        # Verify dates
        dates = sorted([s.date for s in schedules])
        expected_dates = [start_date, start_date + timedelta(days=1), start_date + timedelta(days=2)]
        if dates == expected_dates:
             print("SUCCESS: Dates match exactly.")
        else:
             print(f"FAIL: Dates do not match. Got {dates}")
    else:
        print(f"FAIL: Expected {expected_count} schedules, got {len(schedules)}")

    db.close()

if __name__ == "__main__":
    asyncio.run(run_verification())
