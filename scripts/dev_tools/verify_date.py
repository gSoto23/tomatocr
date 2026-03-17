from datetime import date, datetime
from app.main import format_date_filter

def test_format_date():
    d = date(2023, 10, 27)
    assert format_date_filter(d) == "27-10-2023", f"Failed date: {format_date_filter(d)}"
    
    dt = datetime(2023, 10, 27, 12, 30)
    assert format_date_filter(dt) == "27-10-2023", f"Failed datetime: {format_date_filter(dt)}"
    
    s = "2023-10-27"
    assert format_date_filter(s) == "27-10-2023", f"Failed string ISO: {format_date_filter(s)}"
    
    assert format_date_filter(None) == "", "Failed None"
    
    print("All tests passed!")

if __name__ == "__main__":
    test_format_date()
