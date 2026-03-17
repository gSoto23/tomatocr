
from typing import List
import base64
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType
from pydantic import EmailStr
from app.core.config import settings
from app.db.models.log import DailyLog
from pathlib import Path
from io import BytesIO
from PIL import Image, ImageOps
import tempfile
import os
import logging

logger = logging.getLogger(__name__)

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

from app.db.session import SessionLocal

async def send_log_email(log_id: int, recipients: List[EmailStr], additional_text: str = None):
    """
    Send an email with the log details to the specified recipients.
    """
    temp_files = [] # Track for cleanup initialize early
    db = SessionLocal()
    try:
        log = db.query(DailyLog).filter(DailyLog.id == log_id).first()
        if not log:
            logger.error(f"Cannot send email: Log ID {log_id} not found.")
            return

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



        import requests
        import io
        
        for photo in log.photos:
            try:
                # Handle Remote S3 URLs vs Local Static paths
                if photo.file_path.startswith("http"):
                    response = requests.get(photo.file_path, timeout=10)
                    response.raise_for_status()
                    img_data = io.BytesIO(response.content)
                else:
                    clean_path = photo.file_path.lstrip("/")
                    abs_path = base_path / clean_path
                    if not abs_path.exists():
                        logger.warning(f"Local photo not found: {abs_path}")
                        continue
                    img_data = abs_path
                    
                # Open and Optimize
                with Image.open(img_data) as img:
                    # Fix orientation if needed (EXIF)
                    img = ImageOps.exif_transpose(img)
                    
                    # Convert to RGB (in case of PNG/RGBA) -> JPEG
                    if img.mode in ("RGBA", "P"):
                        img = img.convert("RGB")
                    
                    # Resize (Max 1280px)
                    img.thumbnail((1280, 1280), Image.Resampling.LANCZOS)
                    
                    # Save to Temp File
                    fd, tmp_path = tempfile.mkstemp(suffix=".jpg")
                    with os.fdopen(fd, 'wb') as tmp:
                        img.save(tmp, format="JPEG", quality=80, optimize=True)
                    
                    attachments.append(tmp_path)
                    temp_files.append(tmp_path)

            except Exception as e:
                logger.error(f"Error processing image {photo.file_path}: {e}")
                if not photo.file_path.startswith("http"):
                    attachments.append(str(base_path / photo.file_path.lstrip("/")))
                
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
    except Exception as e:
        import traceback
        import sys
        
        with open("/tmp/email_error.log", "a") as f:
            f.write(f"CRITICAL EMAIL ERROR: {e}\n")
            traceback.print_exc(file=f)

        print(f"CRITICAL EMAIL ERROR: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        logger.error(f"Error sending email: {e}")
    finally:
        # Cleanup temp files
        for tmp_path in temp_files:
            try:
                os.remove(tmp_path)
            except Exception as e:
                logger.error(f"Error removing temp file {tmp_path}: {e}")
        
        # Close DB session
        db.close()
