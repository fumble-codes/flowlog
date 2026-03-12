from rich.panel import Panel
from rich.table import Table as RichTable, box
from rich.text import Text
from rich.console import Group, RenderableType
from rich.align import Align
from rich.columns import Columns
from datetime import datetime
from ui_theme import role_color

def header(title: str):
    """Unified header layout."""
    return Panel(
        Align.center(Text(title.upper(), style=f"bold {role_color('title')}")),
        border_style=role_color("border"),
        box=box.ROUNDED,
        padding=(0, 2)
    )

def footer(hints: str = None):
    """Unified footer layout with keyboard hints."""
    hint_text = hints or "[n] Next • [p] Prev • [q] Quit • [m] Mode • [d] Details"
    return Panel(
        Align.center(Text(hint_text, style=f"dim {role_color('info')}")),
        border_style=role_color("border"),
        box=box.ROUNDED
    )

def smart_tips_panel(tips: list[str]):
    """Contextual tips panel."""
    tip_content = "\n".join([f"💡 {tip}" for tip in tips])
    return Panel(
        tip_content,
        title=f"[bold {role_color('title')}]Tips[/]",
        border_style=role_color("border"),
        box=box.ROUNDED
    )

def grouped_logs_table(entries: list, page: int = 1, page_size: int = 15, mode: str = "compact", show_details: bool = False):
    """
    Renders logs grouped by date with pagination and sorting.
    """
    # 1. Sort: Primary by date (desc), secondary by ID (desc)
    def sort_key(e):
        date = (e.get("date") or e.get("created_at", "")[:10] or "1900-01-01")
        log_id = int(e.get("id", 0))
        return (date, log_id)

    sorted_entries = sorted(entries, key=sort_key, reverse=True)

    # 2. Pagination
    total_pages = (len(sorted_entries) + page_size - 1) // page_size if sorted_entries else 1
    page = max(1, min(page, total_pages))
    start = (page - 1) * page_size
    end = start + page_size
    page_entries = sorted_entries[start:end]

    # 3. Grouping by date
    by_date = {}
    for e in page_entries:
        date = (e.get("date") or e.get("created_at", "")[:10] or "Unknown")
        by_date.setdefault(date, []).append(e)

    # 4. Building the UI components
    renderables = []
    
    for date, items in by_date.items():
        # Date Header
        renderables.append(Text(f"\n📅 {date}", style=f"bold {role_color('title')}"))
        
        table = RichTable(box=box.SIMPLE, border_style=role_color("border"), show_header=True, expand=True)
        table.add_column("ID", style="dim", width=4)
        table.add_column("Title", style=f"bold {role_color('title')}")
        table.add_column("Status", justify="center", width=10)
        table.add_column("Progress", justify="center", width=12)
        table.add_column("Tags", style=f"{role_color('info')}")

        for e in items:
            # Status styling
            status = e.get("status", "TODO").upper()
            status_style = role_color("success") if status == "DONE" else role_color("warning") if status == "WIP" else role_color("info")
            
            # Progress bar/text
            from table_style import render_progress
            prog_val = int(e.get("progress", 0))
            
            # Tags
            tags = e.get("tags", "")
            tags_disp = ", ".join(tags) if isinstance(tags, list) else (tags or "")
            
            table.add_row(
                str(e.get("id", "-")),
                e.get("title", "Untitled"),
                f"[{status_style}]{status}[/]",
                render_progress(prog_val),
                tags_disp
            )
            
            # Collapsible Details (Dense mode or explicit show_details)
            if mode == "dense" or show_details:
                desc = e.get("description", "")
                if desc:
                    table.add_row("", f"[dim]└─ {desc}[/]", "", "", "")

        renderables.append(table)

    # 5. Summary Info
    summary_info = f"Page {page}/{total_pages} • Total Logs: {len(entries)}"
    
    hints = f"[n] Next • [p] Prev • [q] Quit • [m] Mode ({mode}) • [d] Details ({'On' if show_details else 'Off'})"
    
    return Group(
        header(f"Project Logs • {summary_info}"),
        *renderables,
        footer(hints)
    )

