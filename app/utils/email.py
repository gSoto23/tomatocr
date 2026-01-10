
from typing import List
import base64
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType
from pydantic import EmailStr
from app.core.config import settings
from app.db.models.log import DailyLog
from pathlib import Path

# Configure FastMail
conf = ConnectionConfig(
    MAIL_USERNAME=settings.MAIL_USERNAME,
    MAIL_PASSWORD=settings.MAIL_PASSWORD,
    MAIL_FROM=settings.MAIL_FROM,
    MAIL_PORT=settings.MAIL_PORT,
    MAIL_SERVER=settings.MAIL_SERVER,
    MAIL_STARTTLS=settings.MAIL_STARTTLS,
    MAIL_SSL_TLS=settings.MAIL_SSL_TLS,
    USE_CREDENTIALS=True,
    VALIDATE_CERTS=True,
    TEMPLATE_FOLDER=Path(__file__).parent.parent / 'templates'
)

async def send_log_email(log: DailyLog, recipients: List[EmailStr], additional_text: str = None):
    """
    Send an email with the log details to the specified recipients.
    """
    
    # Prepare template context
    # Need to reconstruct logic for tasks (completed vs all)
    completed_task_ids = {entry.task_id for entry in log.task_entries}
    
    # We want to show "Tareas marcadas como done"
    # log.project.tasks contains all tasks of project
    
    done_tasks = []
    if log.project and log.project.tasks:
        for t in log.project.tasks:
            if t.id in completed_task_ids:
                done_tasks.append(t.description)

    # Attachments (Photos)
    # log.photos contains paths relative to static, e.g. /static/uploads/...
    # FastMail needs absolute paths or file objects.
    # Our static files are in app/static
    # Relative path in DB: /static/uploads/2024/01/xxx.jpg
    # Actual path: /Users/gsoto/Desktop/tomatocr/app/static/uploads/2024/01/xxx.jpg
    
    attachments = []
    base_path = Path(__file__).parent.parent # app/
    
    # Add Logo with Content-ID
    logo_path = base_path / 'static/images/logo_tomato.png'
    if logo_path.exists():
        attachments.append({
            "file": str(logo_path),
            "headers": {
                "Content-ID": "<logo_tomato>",
                "Content-Disposition": 'inline; filename="logo_tomato.png"'
            },
            "mime_type": "image",
            "mime_subtype": "png"
        })

    for photo in log.photos:
        # Remove leading slash from /static/...
        clean_path = photo.file_path.lstrip("/")
        abs_path = base_path / clean_path
        if abs_path.exists():
            attachments.append(str(abs_path))
            
    # Subject
    date_str = log.date.strftime('%Y-%m-%d')
    subject = f"Reporte {log.project.name} {date_str}"

    message = MessageSchema(
        subject=subject,
        recipients=recipients,
        template_body={
            "project_name": log.project.name,
            "manager_name": log.user.full_name or log.user.username,
            "date": date_str,
            "notes": log.notes,
            "done_tasks": done_tasks,
            "additional_text": additional_text,
            "log": log # Pass full object just in case
        },
        subtype=MessageType.html,
        attachments=attachments
    )

    fm = FastMail(conf)
    await fm.send_message(message, template_name="emails/log_report.html")
