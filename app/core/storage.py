import boto3
from botocore.exceptions import NoCredentialsError, ClientError
import uuid
import os
import datetime
from app.core.config import settings

class S3Service:
    def __init__(self):
        # We check if credentials exist to instantiate the client properly
        if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
            self.s3_client = boto3.client(
                's3',
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=settings.AWS_REGION
            )
            self.bucket_name = settings.S3_BUCKET_NAME
        else:
            self.s3_client = None
            self.bucket_name = None

    def upload_file(self, file_obj, filename: str, content_type: str = None) -> str:
        """
        Uploads a file object to S3 and returns the public HTTP URL.
        Falls back to local file system if S3 is not configured.
        """
        if not self.s3_client:
            return self._upload_local(file_obj, filename)

        # Generate a unique path: uploads/YYYY/MM/uuid_filename
        now = datetime.datetime.now()
        unique_name = f"{uuid.uuid4().hex}_{filename.replace(' ', '_')}"
        s3_key = f"uploads/{now.year}/{now.month:02d}/{unique_name}"

        extra_args = {}
        if content_type:
            extra_args['ContentType'] = content_type

        try:
            # We assume file_obj is a file-like object (e.g. from FastAPI UploadFile.file)
            self.s3_client.upload_fileobj(
                file_obj,
                self.bucket_name,
                s3_key,
                ExtraArgs=extra_args
            )
            # The bucket is configured for public access, construct URL
            url = f"https://{self.bucket_name}.s3.{settings.AWS_REGION}.amazonaws.com/{s3_key}"
            return url
        except ClientError as e:
            print(f"S3 Upload ClientError: {e}")
            return None
        except Exception as e:
            print(f"S3 Upload Error: {e}")
            return None

    def _upload_local(self, file_obj, filename: str) -> str:
        """
        Fallback mechanism to save files locally inside static/uploads if S3 is down
        or missing from .env
        """
        now = datetime.datetime.now()
        upload_dir = os.path.join("app", "static", "uploads", str(now.year), f"{now.month:02d}")
        os.makedirs(upload_dir, exist_ok=True)
        
        unique_name = f"{uuid.uuid4().hex}_{filename.replace(' ', '_')}"
        file_path = os.path.join(upload_dir, unique_name)
        
        # Ensure we write from the start of the file object
        file_obj.seek(0)
        with open(file_path, "wb") as buffer:
            buffer.write(file_obj.read())
            
        # Return logical local path
        return f"/static/uploads/{now.year}/{now.month:02d}/{unique_name}"

s3_service = S3Service()
