from datetime import datetime, timedelta
from rich.table import Table, box

def make_table(*args, **kwargs):
    """Create a table with thin borders & keep colors."""
    return Table(*args, box=box.MINIMAL, **kwargs)

def get_logical_date(buffer_hours: int = 4) -> str:
    """
    Returns the 'logical' date string (YYYY-MM-DD).
    If the current time is between 12:00 AM and buffer_hours (default 4:00 AM),
    it returns the previous day's date.
    """
    now = datetime.now()
    if now.hour < buffer_hours:
        logical_now = now - timedelta(days=1)
    else:
        logical_now = now
    
    return logical_now.date().isoformat()