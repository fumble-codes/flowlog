import typer 
from rich.console import Console
from datetime import datetime
import sqlite3
from table_style import styled_table as Table
import pyfiglet
from db import init_db
from rich.panel import Panel
from rich.align import Align
import os
from rich.table import box
from rich.align import Align
import pyfiglet
from db import get_status_counts, get_due_on 
from table_style import styled_table as Table
from db import get_db_connection
from validators import validate_title, validate_status
from datetime import datetime
from db import get_all_logs
from db import get_all_logs_with_due
from pathlib import Path
app = typer.Typer()
init_db()  #calling the function from db.py 
app = typer.Typer()
console = Console()
APP_NAME = "Flowlog"
APP_DIR = Path(os.environ.get("APPDATA", Path.home())) / APP_NAME
APP_DIR.mkdir(parents=True, exist_ok=True)

DB_NAME = str(APP_DIR / "flowlog.db")





@app.command() # Function from typer which takes command in cli 
def hello():
    console.print("[bold green ] Welcome to your progress tracker CLI [/]")

@app.command("home")
def home():
    """Flowlog Command Center."""
    today_str = datetime.now().date().isoformat()
    counts = get_status_counts()
    due_today = get_due_on(today_str)

    # Dynamic ASCII logo
    logo_text = pyfiglet.figlet_format("Flowlog", font="slant")
    console.print(Panel.fit(Align.center(f"[cyan]{logo_text}[/cyan]"), border_style="cyan", box=box.ASCII2))

    # Status metrics bar
    metrics = Table(show_header=False)
    metrics.add_column(justify="center")
    metrics.add_column(justify="center")
    metrics.add_column(justify="center")
    metrics.add_row(
        f"[bold yellow]TODO[/]: {counts.get('TODO',0)}",
        f"[bold cyan]WIP[/]: {counts.get('WIP',0)}",
        f"[bold green]DONE[/]: {counts.get('DONE',0)}",
    )
    console.print(metrics)

    # Due today
    due_panel_title = f"[bold red]Due Today • {today_str}[/]"
    if not due_today:
        console.print(Panel.fit("[dim]No tasks due today.[/]", title=due_panel_title, box=box.ASCII2))
    else:
        due_table = Table(title=due_panel_title)
        due_table.add_column("Sr. No.", style="dim", width=8)
        due_table.add_column("Title", style="bold")
        due_table.add_column("Status", style="cyan")
        due_table.add_column("Progress", style="green", justify="right")
        due_table.add_column("Due", style="red")

        for idx, row in enumerate(due_today, start=1):
            _, title, _, status, progress, _, due_date = row
            due_short = (due_date or "").strip()[:10]
            days_left = (datetime.fromisoformat(due_short).date() - datetime.now().date()).days

            if days_left > 0:
                badge = f"{due_short} ([bold]{days_left}[/] day{'s' if days_left!=1 else ''} left)"
            elif days_left == 0:
                badge = f"{due_short} ([bold green]Today![/])"
            else:
                badge = f"{due_short} ([bold red]Overdue[/])"

            due_table.add_row(str(idx), title, status, f"{progress}%", badge)

        console.print(due_table)
    
    #  # --- Urgent tasks table with nearest due dates ---
    logs = get_all_logs_with_due()
    today = datetime.now().date()
    upcoming = []

    for row in logs:
        due_str = row[6]  # due_date is at index 6
        if due_str:
            try:
                due_date_obj = datetime.strptime(due_str, "%Y-%m-%d").date()
                if due_date_obj > today:
                    upcoming.append((due_date_obj, row))
            except ValueError:
                pass

    upcoming.sort(key=lambda x: x[0])
    nearest = upcoming[:5]

    urgent_table = Table(title="[bold red]Urgent Tasks that you need to lock in for • Nearest Due Dates[/]")
    urgent_table.add_column("Sr. No.", style="dim", width=8)
    urgent_table.add_column("Title", style="bold")
    urgent_table.add_column("Status", style="cyan")
    urgent_table.add_column("Progress", style="green", justify="right")
    urgent_table.add_column("Due", style="red")

    if nearest:
        for idx, (due_date_obj, row) in enumerate(nearest, start=1):
            # --- same logic as in view ---
            days_left = (due_date_obj - today).days
            if days_left > 0:
                due_display = f"{due_date_obj} ({days_left} days left)"
            elif days_left == 0:
                due_display = f"{due_date_obj} (Today!)"
            else:
                due_display = f"{due_date_obj} (Overdue!)"

            urgent_table.add_row(
                str(idx),
                row[1],            # title
                row[3],            # status
                f"{row[4]}%",      # progress
                due_display,
            )
    else:
        urgent_table.add_row("-", "No upcoming tasks", "-", "-", "-")

    console.print(urgent_table)






    # Quick tips
    tips = "[italic dim]Tips:[/] [bold]add[/] new task • [bold]view[/] all • [bold]view --td[/] today • [bold]sort[/] logs • [bold]home[/] dashboard • [bold]help[/] for full usage"
    console.print(Panel.fit(tips, box=box.ASCII2))

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    console.print(Align.center(f"[dim]Flowlog • {now_str}[/dim]"))

@app.callback(invoke_without_command=True)
def _default(ctx: typer.Context):
    if ctx.invoked_subcommand is None:
        home()

@app.callback(invoke_without_command=True)
def _default(ctx: typer.Context):
    if ctx.invoked_subcommand is None:
        home()



from db import add_log
from datetime import datetime

@app.command()
def add():
    """Add a new progress log (robust prompts that retry)."""

    # --- Title (required, non-empty) ---
    while True:
        title = typer.prompt("Enter title").strip()
        if title:
            break
        console.print("[red]Title cannot be empty. Try again.[/]")

    # --- Description (optional) ---
    description = typer.prompt("Enter description", default="").strip()

    # --- Status (must be one of TODO/WIP/DONE) ---
    allowed_status = ("TODO", "WIP", "DONE", "FAILED")
    while True:
        status = typer.prompt("Enter the status [TODO/WIP/DONE]", default="TODO").strip().upper()
        if status in allowed_status:
            break
        console.print("[red]Status must be TODO, WIP , FAILED or DONE. Try again.[/]")

    # --- Progress (0–100, blank => 0) ---
    while True:
        progress_str = typer.prompt("Enter progress (0-100)", default="0").strip()
        if progress_str == "":
            progress = 0
            break
        try:
            progress = int(progress_str)
            if 0 <= progress <= 100:
                break
            console.print("[red]Progress must be between 0 and 100. Try again.[/]")
        except ValueError:
            console.print("[red]Progress must be a number. Try again.[/]")

    # --- Tags (optional) ---
    tags = typer.prompt("Enter comma-separated tags (optional)", default="").strip()

    # --- Due date (optional; blank allowed; must be YYYY-MM-DD if provided) ---
    while True:
        due_date_input = typer.prompt("Enter due date (YYYY-MM-DD, optional)", default="").strip()
        if due_date_input == "":
            due_date = None
            break
        try:
            datetime.strptime(due_date_input, "%Y-%m-%d")
            due_date = due_date_input
            break
        except ValueError:
            console.print("[red]Invalid date format. Use YYYY-MM-DD. Try again.[/]")

    # --- Save to DB (no exceptions propagate to user) ---
    try:
        add_log(title, description, status, progress, tags, due_date)
    except Exception as e:
        console.print(f"[red]Failed to save log: {e}[/]")
        return

    console.print(
        f"[green]Log added:[/] {title} - [italic]{status}[/] with progress {progress}%"
        + (f" and tags: [yellow]{tags}[/]" if tags else "")
        + (f" (Due: [bold red]{due_date}[/])" if due_date else "")
    )

from db import get_logs_by_date
from datetime import datetime
from db import get_logs_by_due_date
from db import get_all_logs_with_due
@app.command()
def view(td: bool = typer.Option(False, "--td", help="Show only today's logs")):
    """View logs (optionally only today's)"""
    
    from datetime import datetime
    from db import get_all_logs, get_logs_by_due_date

    # fetch logs
    if td:
        today_str = datetime.now().date().isoformat()
        logs = get_logs_by_due_date(today_str)
    else:
        logs = get_all_logs_with_due()

    if not logs:
        console.print("[bold yellow]No logs found.[/]")
        return

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Sr. No.", style="dim", width=8)
    table.add_column("Title", style="bold")
    table.add_column("Description", style="bold")
    table.add_column("Status", style="cyan")
    table.add_column("Progress", style="green")
    table.add_column("Due Date", style="red")

    for index, log in enumerate(logs, start=1):
        # tuple unpack: id, title, description, status, progress, tags, due_date
        _, title, description, status, progress, _, due_date = log

        # calculate days left if due_date exists
        due_display = ""
        if due_date and due_date != "None":
            try:
                due = datetime.fromisoformat(due_date).date()
                days_left = (due - datetime.now().date()).days
                if days_left > 0:
                    due_display = f"{due} ({days_left} days left)"
                elif days_left == 0:
                    due_display = f"{due} (Today!)"
                else:
                    due_display = f"{due} (Overdue!)"
            except ValueError:
                due_display = due_date  # fallback if format wrong

        table.add_row(str(index), title, description, status, f"{progress}%", due_display)

    console.print(table)
"""============================================================================================================================================================================================"""
    

from db import update_log
from db import get_all_logs
from db import get_log_by_id

@app.command()
def update(
    log_id: int = typer.Argument(..., help="ID of the log to update"),
    title: str = typer.Option(None, "--title", "-t", help="New title"),
    description: str = typer.Option(None, "--desc", "-d", help="New description"),
    status: str = typer.Option(None, "--status", "-s", help="New status (TODO/WIP/DONE/FAILED)"),
    progress: int = typer.Option(None, "--progress", "-p", help="New progress (0–100)"),
    tags: str=typer.Option(None,"--tags","-t2", help="New tags in comma seperated value "),
    due: str = typer.Option(None, "--due", "-d2", help="New due date (YYYY-MM-DD)")
):
    """Updates the log"""
    
    row = get_log_by_id(log_id)
    if not row:
        console.print(f"[red]Log with ID {log_id} not found.[/]")
        raise typer.Exit()

    console.print("[blue]Leave fields empty to keep them unchanged[/]")

    # Title
    while True:
        title = typer.prompt(f"New title? (current: {row[1]})", default=row[1])
        try:
            validate_title(title)
            break
        except Exception as e:
            console.print(f"[red]Invalid title: {e}[/]")

    # Description
    while True:
        description = typer.prompt(f"New description? (current: {row[2]})", default=row[2])
        if description.strip() != "":
            break
        console.print("[red]Description cannot be empty[/]")

    # Status
    while True:
        raw_status = typer.prompt(
            f"New status? (TODO/WIP/DONE/FAIL) (current: {row[3]})",
            default=row[3]
        )
        status = raw_status.strip().upper()  # normalize to all caps

        try:
            validate_status(status)  # validator always receives CAPS
            break
        except Exception as e:
            console.print(f"[red]Invalid status: {e}[/]")

    # Progress
    while True:
        progress_input = typer.prompt(
            f"New progress? (0–100) [current: {row[4]}] (press Enter to keep current)",
            default=""
        )

        if progress_input.strip() == "":
            progress = row[4]  # no change
            break

        try:
            progress = int(progress_input)
            if 0 <= progress <= 100:
                break
            else:
                raise ValueError
        except ValueError:
            console.print("[red]Progress must be a number between 0 and 100[/]")
    # Tags
    tags_input = typer.prompt(
        f"New tags? (comma-separated) [current: {row[7]}] (press Enter to keep current)",
        default=""
    )
    if tags_input.strip() == "":
        tags = row[7]  # keep current
    else:
        tags = tags_input.strip()   
    # Due Date
    while True:
        due_input = typer.prompt(
            f"New due date? (YYYY-MM-DD) [current: {row[8]}] (press Enter to keep current)",
            default=""
        )
        if due_input.strip() == "":
            due = row[8]  # no change
            break
        try:
            datetime.strptime(due_input, "%Y-%m-%d")  # validate format
            due = due_input
            break
        except ValueError:
            console.print("[red]Due date must be in YYYY-MM-DD format[/]")


    # Update log
    update_log(log_id, title, description, status, progress)
    console.print(f"[green]Log ID {log_id} updated successfully![/]")
from datetime import date
from db import carry_log_to_date
@app.command()
def carry(log_id: int):
    """
    Carry a task to today's date using its log ID.
    Also sets the carried task's due_date = today.
    """
    today = datetime.now().date().isoformat()  # 'YYYY-MM-DD'

    result = carry_log_to_date(log_id, today)

    if result == "DONE_TASK":
        console.print(f"[yellow]Task ID {log_id} is already DONE. Cannot carry it.[/]")
    elif result is True:
        console.print(f"[green]Task ID {log_id} successfully carried to {today} (due: {today})[/]")
    else:
        console.print(f"[red]Task ID {log_id} not found.[/]")

from db import delete_log

@app.command()
def delete(log_id: int = typer.Argument(..., help="ID of the log to delete")):
    """Deletes a log using Log id """
    success = delete_log(log_id)
    if not success:
        console.print(f"[red]Log with ID {log_id} not found.[/]")
        return
    console.print(f"[green]Deleted log ID {log_id} successfully.[/]")





import json

@app.command()
def export_json(
    filename: str = typer.Argument("exported_logs.json", help="Filename to export logs as JSON")
):
    """Exports the logs into json format"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id, title, description, status, created_at, updated_at FROM logs ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()

    logs = []
    for row in rows:
        log = {
            "id": row[0],
            "title": row[1],
            "description": row[2],
            "status": row[3],
            "created_at": row[4],
            "updated_at": row[5],
        }
        logs.append(log)

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(logs, f, indent=4)
    console.print(f"[green]Exported {len(logs)} logs to [bold]{filename}[/][/]")
@app.command()
def idmap():
    """shows log id of Logs"""
    logs = get_all_logs()
    if not logs:
        console.print("[bold yellow]No logs found.[/]")
        return

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Log ID", style="bold", width=6)
    table.add_column("Title", style="bold")
    table.add_column("Status", style="cyan")

    for log in logs:
        log_id, title, _, status, *_ = log
        table.add_row(str(log_id), title, status)

    console.print(table)


@app.command()
def details():
    """shows details like created at and updated at """
    from db import get_all_logs_with_tags
    logs = get_all_logs_with_tags()
    
    for log in logs:
        id, title, desc, status, progress, created, updated, tags = log
        print(f"📌 ID: {id}")
        print(f"🔤 Title: {title}")
        print(f"📝 Description: {desc}")
        print(f"📈 Progress: {progress}%")
        print(f"📍 Status: {status}")
        print(f"🏷️ Tags: {tags}")
        print(f"📅 Created: {created}")
        print(f"♻️ Updated: {updated}")
        print("—" * 40)


from rich.progress import Progress, BarColumn, TextColumn, TaskProgressColumn
from rich.panel import Panel
from rich.text import Text
from rich.layout import Layout
from db import get_active_logs  

@app.command("dashboard")
def dashboard():
    """Display active tasks in a dashboard typa layout"""
    logs = get_active_logs()
    if not logs:
        console.print("[bold yellow]No active TODO or WIP tasks found")
        return

    for tasks in logs:
        # ✅ Safe access with defaults
        title = tasks["title"] if "title" in tasks.keys() else ""
        progress_value = tasks["progress"] if "progress" in tasks.keys() and tasks["progress"] is not None else 0
        tags = tasks["tags"] if "tags" in tasks.keys() and tasks["tags"] is not None else ""
        status = tasks["status"] if "status" in tasks.keys() else ""

        # Building single task progress layout
        progress = Progress(
            TextColumn("[bold blue]{task.fields[title]}[/bold blue]", justify="right"),
            BarColumn(),
            TaskProgressColumn(),
            expand=True,
            console=console,
        )

        task_id = progress.add_task("", title=title, total=100, completed=int(progress_value))

        task_panel = Panel.fit(
            progress,
            title=f"[bold green]{title}[/bold green]",
            subtitle=f"[cyan]{status}[/cyan] | [magenta]{tags}[/magenta]",
        )

        with console.capture() as capture:
            progress.start()
            progress.update(task_id, advance=0)
            progress.stop()

        console.print(task_panel)
from db import sort_logs
@app.command("sort")
def sort(
    status: str = typer.Option(None, "--status", "-s", help="Filter by status (TODO/WIP/DONE)"),
    date: str = typer.Option(None, "--date", "-d", help="Filter by creation date (YYYY-MM-DD)"),
    tag: str = typer.Option(None, "--tag", "-t", help="Filter by one or more tags (comma-separated)"),
    sort_by: str = typer.Option(None, "--sort-by", help="Sort by field (created_at/progress/title/status)"),
    order: str = typer.Option(None, "--order", help="Sort order (asc/desc)")
):
    """sorts the logs using filters"""
    if not status:
        status = typer.prompt("Filter by status (TODO/WIP/DONE)?", default="")
        status = status.strip().upper() if status else None

    if not date:
        date = typer.prompt("Filter by date (YYYY-MM-DD)?", default="")
        date = date.strip() if date else None

    if not tag:
        tag = typer.prompt("Filter by tag(s)? (comma-separated)", default="")
        tag = tag.strip() if tag else None

    # Convert comma-separated string to list (or None if empty)
    if tag:
        tag = [t.strip() for t in tag.split(",") if t.strip()]
    else:
        tag = None

    if not sort_by:
        sort_by = typer.prompt("Sort by field (created_at/progress/title/status)?", default="created_at")

    if not order:
        order = typer.prompt("Sort order (asc / desc)?", default="desc")

    try:
        rows = sort_logs(status=status, date=date, tag=tag, sort_by=sort_by, order=order)
    except Exception as e:
        console.print(f"[red]Error while sorting logs: {e}[/]")
        raise typer.Exit()

    if not rows:
        console.print("[yellow]No logs found for the given filters.[/]")
        return

    table = Table(title="Sorted Logs")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Title", style="bold")
    table.add_column("Description", style="dim")
    table.add_column("Status", style="magenta")
    table.add_column("Progress", style="green")
    table.add_column("Tags", style="yellow")
    table.add_column("Created At", style="blue")
    table.add_column("updated at", style="red")

    for row in rows:
        table.add_row(
            str(row[0]),  # ID
            row[1],       # Title
            row[2],       # Description
            row[3],       # Status
            str(row[4]),  # Progress (int → str)
            row[7],       # Tags
            row[5],       # Created At
            row[6],       # Updated At
        )

    console.print(table)
from db import update_tags
@app.command('add-tag')
def add_tag(log_id: int,
            tags: str = typer.Argument("tags",help="Comma-separated tags to add")):
    """Add tag(s) to a log entry """
    row = get_log_by_id(log_id)
    if not row:
        console.print("That log_id doesnt exist")
        raise typer.Exit()
    existing_tags = row[7].split(",") if row[7] else []
    new_tags = [t.strip()for t in tags.split(",") if t.strip()]
    updated_tags = list(set(existing_tags +  new_tags))

    update_tags(log_id, updated_tags)
    console.print(f"[green] Tags updated successfully  for {log_id} [/]")
@app.command('remove-tag')
def remove_tag(log_id: int, 
               tags: str = typer.Argument("tags", help="Comma-separated tags to add")):
    """Remove tags(s) from a log entry"""
    row = get_log_by_id(log_id)
    if not row: 
        console.print("That log id doesnt exist")
        raise typer.Exit()
    existing_tags = row[7].split(",") if row[7] else []
    remove_tags_list = [t.strip() for t in tags.split(",") if t.strip()]
    updated_tags = [t for t in existing_tags if t not in remove_tags_list]

    update_tags(log_id, updated_tags)
    console.print(f"[green]Tags updated successfully for log ID {log_id}[/]")
    
    
    

                        

import csv

@app.command()
def export_csv(
    filename: str = typer.Argument("exported_logs.csv", help="Filename to export logs as CSV")
):
    """exports the logs into csv format"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, description, status, created_at, updated_at FROM logs ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()

    with open(filename, mode='w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["id", "title", "description", "status", "created_at", "updated_at"])
        writer.writerows(rows)

    console.print(f"[green]Exported {len(rows)} logs to [bold]{filename}[/][/]")


import json
import csv
import os

@app.command()
def import_logs(
    filename: str = typer.Argument(..., help="Path to JSON or CSV file to import logs from")
):
    """Import logs from a JSON or CSV file into the database."""
    import os, json, csv
    from datetime import datetime

    if not os.path.isfile(filename):
        console.print(f"[red]File not found:[/] {filename}")
        return

    conn = get_db_connection()
    cursor = conn.cursor()

    def insert_log(log):
        cursor.execute('''
            INSERT INTO logs 
            (title, description, status, progress, created_at, updated_at, tags, due_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            log.get("title", ""),
            log.get("description", ""),
            log.get("status", "TODO"),
            int(log.get("progress", 0)),
            log.get("created_at", datetime.now().isoformat()),
            log.get("updated_at", datetime.now().isoformat()),
            log.get("tags", ""),
            log.get("due_date", None)
        ))

    if filename.endswith(".json"):
        with open(filename, "r", encoding="utf-8") as f:
            try:
                logs = json.load(f)
            except json.JSONDecodeError:
                console.print("[red]Invalid JSON file.[/]")
                return
        for log in logs:
            insert_log(log)

    elif filename.endswith(".csv"):
        with open(filename, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                insert_log(row)

    else:
        console.print("[red]Unsupported file format. Use JSON or CSV.[/]")
        return

    conn.commit()
    conn.close()
    console.print(f"[green]Imported logs from [bold]{filename}[/][/] ✅")
@app.command()
def export_logs(
    filename: str = typer.Argument(..., help="Path to save logs (JSON or CSV format)")
):
    """Export all logs to a JSON or CSV file."""
    import json, csv, os

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM logs")
    rows = cursor.fetchall()

    # Get column names in correct order
    col_names = [description[0] for description in cursor.description]
    conn.close()

    logs = [dict(zip(col_names, row)) for row in rows]

    if filename.endswith(".json"):
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(logs, f, indent=4, ensure_ascii=False)

    elif filename.endswith(".csv"):
        with open(filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=col_names)
            writer.writeheader()
            writer.writerows(logs)

    else:
        console.print("[red]Unsupported file format. Use JSON or CSV.[/]")
        return

    console.print(f"[green]Exported logs to [bold]{filename}[/][/] ✅")

import sys, os

import shlex
import sys

# Only refresh dashboard after commands that modify data
HOME_AFTER = {"add", "delete", "update"}

def interactive_shell():
    console.clear()
    home()

    while True:
        try:
            command_str = input("\n[Flowlog] > ").strip()

            if command_str.lower() in ["exit", "quit"]:
                console.print("\n[bold red]Exiting Flowlog...[/bold red]")
                break

            if command_str:
                args = shlex.split(command_str)
                cmd_name = args[0].lower()

                try:
                    app(args)
                except SystemExit:
                    pass

                # Refresh home screen only for modifying commands
                if cmd_name in HOME_AFTER:
                    console.print()
                    console.clear()
                    home()

        except KeyboardInterrupt:
            console.print("\n[bold red]Exiting Flowlog...[/bold red]")
            break
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        app()
    else:
        interactive_shell()