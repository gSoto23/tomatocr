import asyncio
import os
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
# Adjust import path if needed, usually running from root works with "app.core.config"
# We might need to set PYTHONPATH=.
from app.core.config import settings

async def test_email():
    print("--- Debug Email Configuration ---")
    print(f"MAIL_USERNAME: '{settings.MAIL_USERNAME}'")
    print(f"MAIL_SERVER: '{settings.MAIL_SERVER}'")
    print(f"MAIL_PORT: {settings.MAIL_PORT}")
    print(f"MAIL_FROM: '{settings.MAIL_FROM}'")
    print(f"MAIL_STARTTLS: {settings.MAIL_STARTTLS}")
    print(f"MAIL_SSL_TLS: {settings.MAIL_SSL_TLS}")
    
    # Mask Password
    pwd_len = len(settings.MAIL_PASSWORD) if settings.MAIL_PASSWORD else 0
    print(f"MAIL_PASSWORD: {'*' * pwd_len} (Length: {pwd_len})")
    
    if not settings.MAIL_USERNAME or not settings.MAIL_PASSWORD:
        print("\n[WARNING] Credentials appear empty. Please set MAIL_USERNAME and MAIL_PASSWORD in .env or environment variables.")
    
    conf = ConnectionConfig(
        MAIL_USERNAME=settings.MAIL_USERNAME,
        MAIL_PASSWORD=settings.MAIL_PASSWORD,
        MAIL_FROM=settings.MAIL_FROM,
        MAIL_PORT=settings.MAIL_PORT,
        MAIL_SERVER=settings.MAIL_SERVER,
        MAIL_STARTTLS=settings.MAIL_STARTTLS,
        MAIL_SSL_TLS=settings.MAIL_SSL_TLS,
        USE_CREDENTIALS=True,
        VALIDATE_CERTS=True
    )
    
    message = MessageSchema(
        subject="DEBUG Test Email",
        recipients=["test@example.com"], # Dummy recipient
        body="This is a test email to verify configuration.",
        subtype="plain"
    )
    
    print("\nAttempting to connect and send...")
    try:
        fm = FastMail(conf)
        # We don't expect it to succeed if credentials are bad, but we want the error.
        await fm.send_message(message)
        print("Email sent successfully!")
    except Exception as e:
        print(f"\n[ERROR] Failed to send email: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    try:
        asyncio.run(test_email())
    except Exception as e:
        print(f"Startup Error: {e}")
