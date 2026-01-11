from fastapi.templating import Jinja2Templates
from datetime import datetime

templates = Jinja2Templates(directory="app/templates")

def format_date_filter(value, format_str="%d-%m-%Y"):
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
