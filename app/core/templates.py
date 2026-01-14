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
    
    return cr_time.strftime("%d-%m-%Y %I:%M %p")

templates.env.filters["format_datetime_cr"] = format_datetime_cr_filter
