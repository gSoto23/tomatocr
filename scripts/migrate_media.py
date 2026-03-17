import os
import sys
from pathlib import Path

# Fix relative imports when executing outside Uvicorn (from root folder)
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.base import Base # Load all generic Base models to populate SQLAlchemy metadata registry
from app.db.session import SessionLocal
from app.db.models.log import Photo
from app.core.storage import s3_service
from app.core.config import settings

def migrate_media():
    print(f"Starting Media Migration to S3 Bucket: {settings.S3_BUCKET_NAME}")
    
    if not s3_service.s3_client:
        print("ERROR: S3 Check Failed. Check your AWS variables in .env")
        return

    db = SessionLocal()
    photos = db.query(Photo).all()
    print(f"Total Photos found in Database: {len(photos)}")
    
    migrated_count = 0
    failed_count = 0
    skipped_count = 0
    
    base_dir = Path(__file__).parent.parent / "app"

    for photo in photos:
        # Skip objects already pointing to external resources
        if photo.file_path.startswith("http://") or photo.file_path.startswith("https://"):
            skipped_count += 1
            continue
            
        # Clean relative paths
        clean_path = photo.file_path.lstrip("/")
        abs_path = base_dir / clean_path
        
        if not abs_path.exists():
            print(f"WARNING: File not found locally - {abs_path}")
            failed_count += 1
            continue

        try:
            print(f"Uploading: {photo.file_path}...")
            content_type = "image/jpeg"
            if abs_path.suffix.lower() == ".png":
                content_type = "image/png"
            elif abs_path.suffix.lower() == ".gif":
                content_type = "image/gif"
            elif abs_path.suffix.lower() == ".webp":
                content_type = "image/webp"

            with open(abs_path, "rb") as file_obj:
                s3_url = s3_service.upload_file(file_obj, filename=abs_path.name, content_type=content_type)
            
            if s3_url:
                photo.file_path = s3_url
                db.commit()
                print(f" \u2714 Success -> {s3_url}")
                migrated_count += 1
            else:
                print(f" \u2716 Failed to get S3 URL for {photo.file_path}")
                failed_count += 1
                
        except Exception as e:
            print(f"ERROR processing {photo.file_path}: {e}")
            db.rollback()
            failed_count += 1

    print("\n--- Migration Summary ---")
    print(f"Migrated Successfully: {migrated_count}")
    print(f"Skipped (Already Cloud): {skipped_count}")
    print(f"Failed / Missing File: {failed_count}")

if __name__ == "__main__":
    migrate_media()
