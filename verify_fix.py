import sys
import os

# Add CWD to path
sys.path.append(os.getcwd())

try:
    print("Importing app.db.models.finance...")
    from app.db.models import finance
    print("Success importing finance.")
    
    print("Importing app.main...")
    from app import main
    print("Success importing main.")

except ImportError as e:
    print(f"ImportError: {e}")
    sys.exit(1)
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
