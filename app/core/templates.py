from fastapi.templating import Jinja2Templates
from datetime import datetime

templates = Jinja2Templates(directory="app/templates")

def format_date_filter(value, format_str="%d/%m/%Y"):
    if value is None:
        return ""
    if isinstance(value, str):
        try:
            # Try parsing ISO format
            value = datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            return value
    return value.strftime(format_str)

templates.env.filters["format_date"] = format_date_filter

def format_datetime_cr_filter(value):
    if value is None:
        return ""
    # Ensure value is a datetime object
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return value
    
    # Adjust to Costa Rica Time (UTC-6)
    # Assuming stored time is UTC
    from datetime import timedelta
    cr_time = value - timedelta(hours=6)
    
    return cr_time.strftime("%d/%m/%Y %I:%M %p")

templates.env.filters["format_datetime_cr"] = format_datetime_cr_filter


def to_cr_filter(value):
    """A UTC datetime as Costa Rica time (UTC-6, no daylight saving)."""
    from datetime import timedelta
    return value - timedelta(hours=6) if value else value


templates.env.filters["to_cr"] = to_cr_filter


def static_url(path: str) -> str:
    """/static/<path>?v=<mtime>, so browsers pick up a new version after a deploy."""
    import os
    try:
        version = int(os.path.getmtime(os.path.join("app", "static", path)))
    except OSError:
        version = 0
    return f"/static/{path}?v={version}"


templates.env.globals["static_url"] = static_url


from app.core.roles import ROLE_NAMES  # noqa: E402

templates.env.globals["role_name"] = lambda role: ROLE_NAMES.get(role, role or "")


def crc_filter(value) -> str:
    """Amount in colones: ₡1,234.00 (-₡1,234.00 when negative)."""
    amount = float(value or 0)
    return f"{'-' if amount < 0 else ''}₡{abs(amount):,.2f}"


templates.env.filters["crc"] = crc_filter


def long_date_weekday(day) -> str:
    """lunes 28 de septiembre de 2026 (not dependent on the server locale)."""
    from app.utils.company import long_date
    weekdays = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
    return f"{weekdays[day.weekday()]} {long_date(day)}"


templates.env.globals["long_date"] = long_date_weekday


def _today_cr():
    from app.utils.timecr import today_cr
    return today_cr()


templates.env.globals["today_cr"] = _today_cr
