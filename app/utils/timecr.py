"""Costa Rica time. The server runs in UTC; Costa Rica is UTC-6 all year (no DST)."""
from datetime import date, datetime, timedelta

CR_OFFSET = timedelta(hours=6)


def now_cr() -> datetime:
    return datetime.utcnow() - CR_OFFSET


def today_cr() -> date:
    return now_cr().date()
