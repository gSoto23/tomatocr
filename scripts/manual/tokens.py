"""Session tokens of the fictitious manual users, one per role (JSON on stdout).
Used by scripts/manual/capturas.mjs against the LOCAL demo server only: the tokens
are signed with the local SECRET_KEY and the users exist only in the demo database."""
import json
import os
import sys
from datetime import timedelta

sys.path.insert(0, os.path.dirname(__file__))

from app.core.security import create_access_token  # noqa: E402
from datos_demo import DEMO_USERS  # noqa: E402

print(json.dumps({role: create_access_token({"sub": username}, timedelta(hours=2))
                  for role, (username, _) in DEMO_USERS.items()}))
