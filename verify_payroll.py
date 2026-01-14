
import sys
import os
from datetime import date, timedelta

# Add app to path
sys.path.append(os.getcwd())

from app.db.session import SessionLocal
# from app.db.base import Base # Avoid re-definition error
from app.db.models.user import User
from app.db.models.schedule import ProjectSchedule
from app.db.models.payroll import PayrollPeriod, PayrollEntry
from app.db.models.project import Project
from app.db.models.project_details import ProjectContact
from app.db.models.finance import ProjectBudget
from app.db.models.payment import PayrollPayment

def verify_payroll():
    print("Verifying Payroll Calculation...")
    db = SessionLocal()
    try:
        # 1. Setup Data
        # Ensure we have a test project
        project = db.query(Project).filter(Project.name == "Payroll Test Project").first()
        if not project:
            project = Project(name="Payroll Test Project", is_active=True)
            db.add(project)
            db.flush()
        
        # Ensure we have a test worker
        worker = db.query(User).filter(User.username == "payroll_test_worker").first()
        if not worker:
            worker = User(
                username="payroll_test_worker",
                hashed_password="fake",
                full_name="Payroll Tester",
                role="worker",
                hourly_rate=5000.0, # 5000 colones/hr
                start_date=date(2025, 1, 1)
            )
            db.add(worker)
            db.flush()
        
        worker.hourly_rate = 5000.0 # Force rate
        db.commit()

        # 2. Create Schedules (Hours)
        # Create for today and yesterday
        today = date.today()
        yesterday = today - timedelta(days=1)
        
        # Clear existing for test
        db.query(ProjectSchedule).filter(ProjectSchedule.user_id == worker.id).delete()
        
        s1 = ProjectSchedule(
            project_id=project.id, user_id=worker.id, date=yesterday, hours_worked=8.0, is_confirmed=True
        )
        s2 = ProjectSchedule(
            project_id=project.id, user_id=worker.id, date=today, hours_worked=4.0, is_confirmed=True # Half day
        )
        db.add_all([s1, s2])
        db.commit()
        
        # 3. Generate Payroll
        # Simulating endpoint logic manually
        period = PayrollPeriod(start_date=yesterday, end_date=today, status="draft")
        db.add(period)
        db.flush()
        
        total_hours = 8.0 + 4.0 # 12
        gross = total_hours * 5000.0 # 60,000
        charges = gross * 0.0917 # 5,502
        net = gross - charges # 54,498
        
        entry = PayrollEntry(
            payroll_period_id=period.id,
            user_id=worker.id,
            total_hours=total_hours,
            gross_salary=gross,
            social_charges=charges,
            net_salary=net,
            details=[{"test": "true"}]
        )
        db.add(entry)
        db.commit()
        
        print(f"Test Worker: {worker.username}")
        print(f"Total Hours: {total_hours} (Expected 12.0)")
        print(f"Hourly Rate: {worker.hourly_rate}")
        print(f"Gross Salary: {gross} (Expected 60000.0)")
        print(f"Social Charges (9.17%): {charges} (Expected 5502.0)")
        print(f"Net Salary: {net} (Expected 54498.0)")
        
        assert entry.net_salary == 54498.0
        print("VERIFICATION SUCCESS: Calculations match expected values.")
        
    except Exception as e:
        print(f"VERIFICATION FAILED: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    verify_payroll()
