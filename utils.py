from rich.table import Table, box

def make_table(*args, **kwargs):
    """Create a table with thin borders & keep colors."""
    return Table(*args, box=box.MINIMAL, **kwargs)