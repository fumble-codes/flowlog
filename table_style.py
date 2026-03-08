from rich.table import Table, box
from rich.progress_bar import ProgressBar

def styled_table(*args, **kwargs):
    # Always ASCII2 borders, but still allow overrides
    kwargs.setdefault("box", box.ASCII2)  # ASCII2 = clean ASCII-style table
    kwargs.setdefault("show_header", True)
    kwargs.setdefault("header_style", "bold magenta")
    return Table(*args, **kwargs)

def render_progress(progress: int):
    """Render a progress bar as a string for use in a table cell."""
    color = "green" if progress == 100 else "cyan" if progress > 0 else "red"
    return ProgressBar(total=100, completed=progress, width=15, style=f"dim {color}", complete_style=color)