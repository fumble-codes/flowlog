from rich.table import Table, box

def styled_table(*args, **kwargs):
    # Always ASCII2 borders, but still allow overrides
    kwargs.setdefault("box", box.ASCII2)  # ASCII2 = clean ASCII-style table
    kwargs.setdefault("show_header", True)
    kwargs.setdefault("header_style", "bold magenta")
    return Table(*args, **kwargs)