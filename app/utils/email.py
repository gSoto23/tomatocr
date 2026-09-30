import re

from typing import List
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType
from pydantic import EmailStr
from app.core.config import settings
from app.db.models.log import DailyLog
from pathlib import Path
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
    MAIL_FROM_NAME=settings.MAIL_FROM_NAME,
    MAIL_PORT=settings.MAIL_PORT,
    MAIL_SERVER=settings.MAIL_SERVER,
    MAIL_STARTTLS=settings.MAIL_STARTTLS,
    MAIL_SSL_TLS=settings.MAIL_SSL_TLS,
    USE_CREDENTIALS=True,
    VALIDATE_CERTS=True,
    TEMPLATE_FOLDER=Path(__file__).parent.parent / 'templates'
)

from app.db.session import SessionLocal

async def send_log_email(log_id: int, recipients: List[EmailStr], additional_text: str = None, custom_notes: str = None,
                         bcc: List[str] = None) -> bool:
    """
    Send an email with the log details to the specified recipients (and a blind copy).
    Returns True only when the mail server accepted it, so the screen can say so.
    """
    temp_files = [] # Track for cleanup initialize early
    db = SessionLocal()
    try:
        log = db.query(DailyLog).filter(DailyLog.id == log_id).first()
        if not log:
            logger.error(f"Cannot send email: Log ID {log_id} not found.")
            return False

        # Tasks marked done, from the report's own entries, so a task later archived still appears.
        done_tasks = [entry.task.description for entry in sorted(log.task_entries, key=lambda e: e.task_id)
                      if entry.task is not None]

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
            bcc=list(bcc or []),
            template_body={
                "project_name": log.project.name,
                "location_name": log.location.name if log.location else None,
                "location_waze": log.location.waze_pin if log.location else None,
                "manager_name": log.user.full_name or log.user.username,
                "date": date_str,
                "notes": custom_notes if custom_notes is not None else log.notes,
                "done_tasks": done_tasks,
                "additional_text": additional_text,
                "log": log # Pass full object just in case
            },
            subtype=MessageType.html,
            attachments=attachments
        )

        fm = FastMail(conf)
        await fm.send_message(message, template_name="emails/log_report.html")
        return True
    except Exception as e:
        import traceback
        import sys
        
        with open("/tmp/email_error.log", "a") as f:
            f.write(f"CRITICAL EMAIL ERROR: {e}\n")
            traceback.print_exc(file=f)

        print(f"CRITICAL EMAIL ERROR: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        logger.error(f"Error sending email: {e}")
        return False
    finally:
        # Cleanup temp files
        for tmp_path in temp_files:
            try:
                os.remove(tmp_path)
            except Exception as e:
                logger.error(f"Error removing temp file {tmp_path}: {e}")
        
        # Close DB session
        db.close()



async def send_plain_email(recipients: List[str], subject: str, body: str):
    """Short internal notification (new leads). Does nothing if mail isn't configured."""
    recipients = sorted({r for r in recipients if r})
    if not recipients or not settings.MAIL_USERNAME:
        return
    try:
        message = MessageSchema(subject=subject, recipients=recipients, body=body, subtype=MessageType.plain)
        await FastMail(conf).send_message(message)
    except Exception as e:
        logger.error(f"Error sending notification '{subject}': {e}")


# The signature of every quote e-mail: the company, not the seller (the seller takes over
# when the client replies). Same look as the TOMATO mail signature.
SIGNATURE = {"name": "TOMATO CR", "phone": "+506 7080 8613", "web": "www.tomatocr.com"}
SIGNATURE_LOGO = Path(__file__).parent.parent / "static" / "cotizador" / "LogoTomatoB.png"


async def send_quote_email(recipients: List[str], subject: str, message: str, pdf: bytes, filename: str,
                           reply_to: List[str]) -> bool:
    """A quote to the client, with its PDF attached and the TOMATO signature; the client's
    reply goes to the seller (reply_to). Returns True only when the mail server accepted it."""
    if not settings.MAIL_USERNAME:
        logger.error("Quote e-mail not sent: mail is not configured")
        return False
    folder = tempfile.mkdtemp()
    path = os.path.join(folder, filename)
    try:
        with open(path, "wb") as f:
            f.write(pdf)
        attachments = [{"file": path, "mime_type": "application", "mime_subtype": "pdf"}]
        if SIGNATURE_LOGO.exists():
            attachments.append({"file": str(SIGNATURE_LOGO), "mime_type": "image", "mime_subtype": "png",
                                "headers": {"Content-ID": "<firma_tomato>",
                                            "Content-Disposition": 'inline; filename="tomato.png"'}})
        email = MessageSchema(subject=subject, recipients=recipients, body=message_html(message),
                              subtype=MessageType.html, reply_to=[r for r in reply_to if r],
                              attachments=attachments)
        await FastMail(conf).send_message(email)
        return True
    except Exception as e:
        logger.error(f"Error sending quote '{subject}': {e}")
        return False
    finally:
        try:
            os.remove(path)
            os.rmdir(folder)
        except OSError:
            pass


QUOTE_NUMBER = re.compile(r"\b(TCR)-(\d{4})-(\d+)\b")


def message_html(message: str) -> str:
    """The text the seller wrote (escaped, line breaks kept) and the TOMATO signature with its
    logo. Quote numbers use non-breaking hyphens so Gmail doesn't turn them into phone links."""
    from html import escape
    text = QUOTE_NUMBER.sub("\\1\u2011\\2\u2011\\3", message.strip())
    paragraphs = "".join(f'<p style="margin:0 0 12px">{escape(block).replace(chr(10), "<br>")}</p>'
                         for block in text.split("\n\n"))
    s = SIGNATURE
    label = 'style="font-weight:700"'
    signature = (
        '<div style="margin-top:20px;color:#222">--'
        f'<p style="margin:12px 0 6px;font-weight:700">{s["name"]}</p>'
        f'<p style="margin:0 0 6px"><span {label}>Tel.</span> {s["phone"]}</p>'
        f'<p style="margin:0 0 12px"><span {label}>Web:</span> <a href="https://{s["web"]}" style="color:#1a56db">{s["web"]}</a></p>'
        '<img src="cid:firma_tomato" alt="TOMATO" width="180" style="display:block;width:180px;height:auto"></div>'
    )
    return ('<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:1.5;color:#1f2937">'
            f"{paragraphs}{signature}</div>")
