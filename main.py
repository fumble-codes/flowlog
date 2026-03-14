import warnings
import os
# Suppress specific dependency and deprecation warnings
warnings.filterwarnings("ignore", category=UserWarning, module="requests")
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", message=".*google.generativeai.*")
os.environ["PYTHONWARNINGS"] = "ignore"

import typer 
import os
import pyfiglet
import json
import csv
import shlex
import sys
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from rich.console import Console, Group
from rich.text import Text
from rich.panel import Panel
from rich.align import Align
from rich.table import Table as RichTable, box
from rich.progress import Progress, BarColumn, TextColumn, TaskProgressColumn

# Global exception handler to prevent crashes
def exception_handler(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    console = Console()
    console.print(f"\n[bold red]Error:[/] {exc_type.__name__}: {exc_value}")
    console.print("[dim]Type 'flowlog --help' for available commands.[/]")

sys.excepthook = exception_handler

# Internal imports
from db import (
    init_db, 
    get_status_counts, 
    get_due_on, 
    get_db_connection, 
    get_all_logs, 
    get_all_logs_with_due,
    add_log,
    update_log,
    get_log_by_id,
    delete_log,
    carry_log_to_date,
    sort_logs,
    get_active_logs,
    update_tags,
    get_all_logs_with_tags,
    get_logs_by_due_date
)
from table_style import styled_table as Table, render_progress
from validators import validate_title, validate_status
from ai_utils import (
    smart_parse_task, 
    generate_ai_summary, 
    study_user_patterns, 
    get_real_time_context,
    infer_tags_local,
    AIApiError
)
from gap_recovery import check_and_run_gap_recovery
from gap_recovery import rehydrate_gap_summaries
from ui import header, footer, grouped_logs_table, smart_tips_panel
from ui_theme import role_color

# Load environment variables
load_dotenv()

def trigger_ai_study(force: bool = False):
    """
    Automatically study user patterns if logs have been updated since last study.
    """
    from db import get_last_log_time, get_ai_memory, update_ai_memory, get_all_logs_with_tags
    
    last_log_time = get_last_log_time()
    profile, last_study_time = get_ai_memory("user_profile")
    
    # Study if force=True OR no profile exists OR logs updated after last study
    if force or not profile or (last_log_time and last_study_time and last_log_time > last_study_time):
        # We explicitly get logs with tags and ensure we have log_date for the AI
        logs = [dict(row) for row in get_all_logs_with_tags()]
        if logs:
            new_profile = study_user_patterns(logs)
            if new_profile:
                update_ai_memory("user_profile", new_profile)
                return new_profile
    return profile

# App Setup
app = typer.Typer(help="Flowlog: A modern CLI project tracker with AI insights.", add_completion=False)
console = Console()

# TUI Stability Patch: Disable live status if running inside Textual
if os.environ.get("FLOWLOG_TUI_MODE") == "1":
    from contextlib import contextmanager
    @contextmanager
    def dummy_status(status, *args, **kwargs):
        yield
    console.status = dummy_status

# Ensure DB directory exists
APP_NAME = "Flowlog"
APP_DIR = Path(os.environ.get("APPDATA", Path.home())) / APP_NAME
APP_DIR.mkdir(parents=True, exist_ok=True)
DB_NAME = str(APP_DIR / "flowlog.db")

# Initialize DB on start
init_db()

# Try to import click_repl, fallback to custom REPL if not available
try:
    import click_repl
    CLICK_REPL_AVAILABLE = True
except ImportError:
    CLICK_REPL_AVAILABLE = False

def custom_repl(ctx: typer.Context):
    """Simple fallback REPL if click_repl is not available."""
    console.print("[dim]Enter commands one at a time. Type 'exit' to quit.[/]\n")
    while True:
        try:
            cmd = console.input("[cyan]> [/]")
            if cmd.strip().lower() in ('exit', 'quit', 'q'):
                break
            if not cmd.strip():
                continue
            ctx.invoke(ctx.command, args=shlex.split(cmd))
        except KeyboardInterrupt:
            console.print("\n[yellow]Use 'exit' to quit.[/]")
        except Exception as e:
            console.print(f"[red]Error: {e}[/]")

# --- Callbacks ---
@app.callback(invoke_without_command=True)
def _default(ctx: typer.Context):
    if ctx.invoked_subcommand is None:
        home()
        import sys
        if sys.stdout.isatty():
            console.print("\n[bold cyan]Entering Interactive Mode. Type commands (e.g., 'ai-add \"task\"', 'insights'). Type 'exit' to quit.[/]\n")
            if CLICK_REPL_AVAILABLE:
                try:
                    click_repl.repl(ctx)
                except Exception as e:
                    console.print(f"[yellow]REPL unavailable: {e}[/]")
                    custom_repl(ctx)
            else:
                custom_repl(ctx)

# --- Core Commands ---

@app.command()
def hello():
    """Welcome message."""
    console.print("[bold green]Welcome to Flowlog - Your AI-Powered Progress Tracker![/]")

@app.command("home")
def home():
    """Flowlog Command Center Dashboard."""
    from utils import get_logical_date
    today_str = get_logical_date()
    counts = get_status_counts()
    due_today = get_due_on(today_str)

    # Dynamic ASCII logo
    logo_text = pyfiglet.figlet_format("Flowlog", font="slant")
    console.print(Panel.fit(Align.center(f"[cyan]{logo_text}[/cyan]"), border_style="cyan", box=box.ASCII2))

    # Status metrics bar
    metrics = RichTable(show_header=False, box=box.ASCII2)
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
        due_table = RichTable(title=due_panel_title, box=box.ASCII2)
        due_table.add_column("Sr. No.", style="dim", width=8)
        due_table.add_column("Title", style="bold")
        due_table.add_column("Status", style="cyan")
        due_table.add_column("Progress", width=20)
        due_table.add_column("Due", style="red")

        for idx, row in enumerate(due_today, start=1):
            # id, title, description, status, progress, tags, due_date
            _, title, _, status, progress, _, due_date = row
            due_short = (due_date or "").strip()[:10]
            try:
                days_left = (datetime.fromisoformat(due_short).date() - datetime.now().date()).days
                if days_left > 0:
                    badge = f"{due_short} ([bold]{days_left}[/] day{'s' if days_left!=1 else ''} left)"
                elif days_left == 0:
                    badge = f"{due_short} ([bold green]Today![/])"
                else:
                    badge = f"{due_short} ([bold red]Overdue[/])"
            except:
                badge = due_short

            due_table.add_row(str(idx), title, status, render_progress(progress), badge)
        console.print(due_table)
    
    # Urgent tasks
    logs = get_all_logs_with_due()
    today = datetime.now().date()
    upcoming = []
    for row in logs:
        # id, title, description, status, progress, tags, due_date
        due_str = row[6]
        if due_str and due_str != "None":
            try:
                due_date_obj = datetime.strptime(due_str[:10], "%Y-%m-%d").date()
                if due_date_obj > today:
                    upcoming.append((due_date_obj, row))
            except ValueError: pass

    upcoming.sort(key=lambda x: x[0])
    nearest = upcoming[:5]

    urgent_table = RichTable(title="[bold red]Urgent Tasks • Nearest Due Dates[/]", box=box.ASCII2)
    urgent_table.add_column("Sr. No.", style="dim", width=8)
    urgent_table.add_column("Title", style="bold")
    urgent_table.add_column("Status", style="cyan")
    urgent_table.add_column("Progress", width=20)
    urgent_table.add_column("Due", style="red")

    if nearest:
        for idx, (due_date_obj, row) in enumerate(nearest, start=1):
            days_left = (due_date_obj - today).days
            due_display = f"{due_date_obj} ({days_left} days left)"
            urgent_table.add_row(str(idx), row[1], row[3], render_progress(row[4]), due_display)
    else:
        urgent_table.add_row("-", "No upcoming tasks", "-", "-", "-")

    console.print(urgent_table)

    tips = "[italic dim]Tips:[/] [bold]ai-add[/] \"task\" • [bold]ai-summary[/] • [bold]insights[/] • [bold]details[/] • [bold]dashboard[/]"
    console.print(Panel.fit(tips, box=box.ASCII2))
    console.print(Align.center(f"[dim]Flowlog • {datetime.now().strftime('%Y-%m-%d %H:%M')}[/dim]"))

@app.command()
def add():
    """Add a new progress log manually."""
    check_and_run_gap_recovery()
    title = typer.prompt("Enter title").strip()
    while not title:
        console.print("[red]Title cannot be empty.[/]")
        title = typer.prompt("Enter title").strip()

    description = typer.prompt("Enter description", default="").strip()
    allowed_status = ("TODO", "WIP", "DONE", "FAILED")
    status = typer.prompt("Enter status [TODO/WIP/DONE/FAILED]", default="TODO").strip().upper()
    while status not in allowed_status:
        console.print(f"[red]Status must be one of {allowed_status}.[/]")
        status = typer.prompt("Enter status", default="TODO").strip().upper()

    progress = typer.prompt("Enter progress (0-100)", default="0")
    try:
        progress = int(progress)
    except:
        progress = 0

    tags = typer.prompt("Enter comma-separated tags (optional)", default="").strip()
    due_date = typer.prompt("Enter due date (YYYY-MM-DD, optional)", default="").strip()
    if due_date:
        try:
            datetime.strptime(due_date, "%Y-%m-%d")
        except:
            due_date = "None"
    else:
        due_date = "None"

    try:
        new_id = add_log(title, description, status, progress, tags, due_date)
        console.print(f"[green]Log added successfully! (ID: {new_id})[/]")
        console.print(f"[dim]Tip: Undo this with 'delete {new_id}'[/]")
    except Exception as e:
        console.print(f"[red]Failed to save log: {e}[/]")

@app.command()
def details(log_id: int = typer.Argument(None, help="Specific ID to show details for. If omitted, shows all logs.")):
    """Shows full details of logs (Description, Tags, Timestamps, etc.)"""
    from db import get_all_logs_with_tags, get_log_by_id
    
    if log_id:
        row = get_log_by_id(log_id)
        if not row:
            console.print(f"[red]Log with ID {log_id} not found.[/]")
            return
        logs = [row]
    else:
        logs = get_all_logs_with_tags()

    if not logs:
        console.print("[bold yellow]No logs found.[/]")
        return

    for log in logs:
        # Handling both Row objects and tuples for backward compatibility
        try:
            # id, title, desc, status, progress, created, updated, tags, log_date
            id, title, desc, status, progress, created, updated, tags, event_date = log
        except:
            id = log["id"]
            title = log["title"]
            desc = log["description"]
            status = log["status"]
            progress = log["progress"]
            created = log["created_at"]
            updated = log["updated_at"]
            tags = log["tags"]
            event_date = log.get("log_date")

        panel_content = (
            f"📅 [bold cyan]Event Date:[/] {event_date or 'N/A'}\n"
            f"🔤 [bold cyan]Title:[/] {title}\n"
            f"📝 [bold cyan]Description:[/] {desc or 'N/A'}\n"
            f"📈 [bold cyan]Progress:[/] {render_progress(progress)} {progress}%\n"
            f"📍 [bold cyan]Status:[/] {status}\n"
            f"🏷️ [bold cyan]Tags:[/] {tags or 'None'}\n"
            f"🕒 [bold cyan]Created:[/] {created}\n"
            f"♻️ [bold cyan]Updated:[/] {updated}"
        )
        console.print(Panel(panel_content, title=f"📌 Log ID: {id}", border_style="blue", expand=False))

@app.command()
def view(
    mode: str = typer.Option("compact", "--mode", "-m", help="compact or dense"),
    page_size: int = typer.Option(15, "--size", "-s", help="Logs per page")
):
    """View logs with interactive pagination."""
    rows = get_all_logs_with_due()
    if not rows:
        console.print("[bold yellow]No logs found.[/]")
        return

    # Convert tuples to dicts for the UI component
    entries = []
    for r in rows:
        # r: id, title, description, status, progress, tags, due_date, log_date
        entries.append({
            "id": r[0],
            "title": r[1],
            "description": r[2],
            "status": r[3],
            "progress": r[4],
            "tags": r[5].split(",") if r[5] else [],
            "date": r[7] or (r[6] if r[6] != "None" else None) or "Unknown"
        })

    page = 1
    show_details = (mode == "dense")
    
    while True:
        console.clear()
        console.print(grouped_logs_table(entries, page=page, page_size=page_size, mode=mode, show_details=show_details))
        
        cmd = typer.prompt("", prompt_suffix="[n/p/m/d/q] > ", default="q").lower().strip()
        
        if cmd == "n":
            page += 1
        elif cmd == "p":
            page -= 1
        elif cmd == "m":
            mode = "dense" if mode == "compact" else "compact"
        elif cmd == "d":
            show_details = not show_details
        elif cmd == "q":
            break

@app.command()
def update(
    log_id: int = typer.Argument(..., help="ID of the log to update"),
    title: str = typer.Option(None, "--title", "-t"),
    desc: str = typer.Option(None, "--desc", "-d"),
    status: str = typer.Option(None, "--status", "-s"),
    progress: int = typer.Option(None, "--progress", "-p")
):
    """Update an existing log."""
    row = get_log_by_id(log_id)
    if not row:
        console.print(f"[red]Log {log_id} not found.[/]")
        return

    # If no options provided, enter interactive mode
    if not any([title, desc, status, progress]):
        if os.environ.get("FLOWLOG_TUI_MODE") == "1":
            console.print("[red]Interactive update not supported from TUI command line. Use the 'Logs' tab selection instead.[/]")
            return
        title = typer.prompt("New title?", default=row[1])
        desc = typer.prompt("New description?", default=row[2])
        status = typer.prompt("New status?", default=row[3]).upper()
        progress_str = typer.prompt("New progress?", default=str(row[4]))
        progress = int(progress_str)

    update_log(log_id, title, desc, status, progress)
    console.print(f"[green]Log {log_id} updated successfully![/]")
    console.print(f"[dim]Tip: You can revert changes using interactive 'update {log_id}' again.[/]")

@app.command()
def delete(log_id: int):
    """Delete a log."""
    if delete_log(log_id):
        console.print(f"[green]Deleted log {log_id}.[/]")
        console.print("[dim]Note: Deletions are permanent in the current version.[/]")
    else:
        console.print(f"[red]Log {log_id} not found.[/]")

@app.command()
def carry(log_id: int):
    """Carry a task to today."""
    today = datetime.now().date().isoformat()
    result = carry_log_to_date(log_id, today)
    if result == "DONE_TASK":
        console.print("[yellow]Task is already DONE.[/]")
    elif result:
        console.print(f"[green]Task {log_id} carried to {today}.[/]")
    else:
        console.print(f"[red]Task {log_id} not found.[/]")

@app.command()
def undo():
    """Undo the last added log."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, title FROM logs ORDER BY created_at DESC LIMIT 1")
    row = cursor.fetchone()
    if not row:
        console.print("[yellow]Nothing to undo.[/]")
        conn.close()
        return
    
    log_id, title = row[0], row[1]
    confirmed = True
    if os.environ.get("FLOWLOG_TUI_MODE") != "1":
        confirmed = typer.confirm(f"Delete the last added log: '{title}' (ID: {log_id})?", default=True)
    
    if confirmed:
        cursor.execute("DELETE FROM logs WHERE id = ?", (log_id,))
        conn.commit()
        console.print(f"[green]Log '{title}' successfully deleted.[/]")
    conn.close()

# --- View & Search Commands ---

@app.command()
def search(query: list[str] = typer.Argument(..., help="Search query (can be multiple words)")):
    """Search tasks by title, description or tags."""
    query_str = " ".join(query)
    conn = get_db_connection()
    cursor = conn.cursor()
    q = f"%{query_str}%"
    cursor.execute("SELECT * FROM logs WHERE title LIKE ? OR description LIKE ? OR tags LIKE ?", (q, q, q))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        console.print(f"[yellow]No results for '{query_str}'.[/]")
        return

    table = Table(title=f"Search Results: {query_str}")
    table.add_column("ID", width=6)
    table.add_column("Title")
    table.add_column("Status")
    table.add_column("Progress", width=20)
    for row in rows:
        table.add_row(str(row[0]), row[1], row[3], render_progress(row[4]))
    console.print(table)

@app.command()
def dashboard():
    """Live dashboard of active tasks."""
    logs = get_active_logs()
    if not logs:
        console.print("[bold yellow]No active tasks. Try adding one or checking [bold]insights[/] for what to do next![/]")
        return

    for task in logs:
        progress = Progress(
            TextColumn("[bold blue]{task.fields[title]}[/bold blue]", justify="right"),
            BarColumn(),
            TaskProgressColumn(),
            expand=True,
            console=console,
        )
        task_id = progress.add_task("", title=task["title"], total=100, completed=task["progress"] or 0)
        task_panel = Panel.fit(
            progress,
            title=f"[bold green]{task['title']}[/bold green]",
            subtitle=f"{task['status']} | {task['tags'] or 'No tags'}",
        )
        # Mocking live update for static display
        with console.capture() as capture:
            progress.start(); progress.update(task_id, advance=0); progress.stop()
        console.print(task_panel)

@app.command()
def summary():
    """Project statistics summary."""
    counts = get_status_counts()
    total = sum(counts.values())
    if total == 0:
        console.print("[yellow]No tasks to summarize.[/]")
        return

    done = counts.get("DONE", 0)
    rate = (done / total) * 100
    
    stats_table = RichTable(show_header=False, box=box.SIMPLE, expand=True)
    stats_table.add_column(style="bold")
    stats_table.add_column(justify="right")
    stats_table.add_row("Total Tasks", str(total))
    stats_table.add_row("TODO", f"[bold {role_color('warning')}]{counts.get('TODO',0)}[/]")
    stats_table.add_row("WIP", f"[bold {role_color('title')}]{counts.get('WIP',0)}[/]")
    stats_table.add_row("DONE", f"[bold {role_color('success')}]{done}[/]")
    
    panel = Panel(
        Group(
            stats_table,
            Text(f"\nCompletion: {rate:.1f}%", justify="center", style="bold"),
            Align.center(render_progress(int(rate)))
        ),
        title="📊 Project Stats", border_style="magenta"
    )
    console.print(panel)

# --- AI Commands ---

@app.command("force-study")
def force_study():
    """Manually force the AI to re-study all your logs and update your profile."""
    with console.status("[bold blue]AI is performing a deep study of all your logs...[/]"):
        profile = trigger_ai_study(force=True)
    if profile:
        console.print("[bold green]Deep study complete! Your profile has been updated.[/]")
        insights()
    else:
        console.print("[red]Failed to update profile. Check your logs and API key.[/]")

@app.command("insights")
def insights():
    """Get a deep psychological and behavioral analysis of your productivity."""
    try:
        user_profile_json = trigger_ai_study()
    except AIApiError as e:
        console.print(f"\n[bold red]🧠 AI Service Error:[/] {e}")
        return
        
    if not user_profile_json:
        console.print("[bold yellow]Not enough data to generate insights yet. Keep logging![/]")
        return

    try:
        profile = json.loads(user_profile_json)
    except Exception as e:
        console.print(f"[red]Error parsing user profile: {e}[/]")
        return

    # Create a rich layout for insights
    title = f"[bold magenta][BRAIN] Deep Productivity Insights[/]"
    
    # Archetypes as badges
    archetypes_str = " ".join([f"[bold cyan on blue] {a} [/]" for a in profile.get('archetypes', [])])
    
    from rich.markup import Markup
    
    # Summary panel
    summary_panel = Panel(
        f"{Markup.escape(profile.get('summary', 'No summary available.'))}\n\n"
        f"[bold cyan]Archetypes:[/] {archetypes_str}\n"
        f"[bold cyan]Working Hours:[/] {Markup.escape(profile.get('working_hours', 'Unknown'))}",
        title="[bold blue]Overview[/]",
        border_style="blue"
    )

    # Focus breakdown
    focus_str = "\n".join([f"- {Markup.escape(f)}" for f in profile.get('focus_breakdown', [])])
    focus_panel = Panel(focus_str, title="[bold green]Focus Breakdown[/]", border_style="green")

    # Psychological Profile
    psyche_panel = Panel(
        f"{Markup.escape(profile.get('psychological_profile', 'No analysis available.'))}",
        title="[bold yellow]Psychological Profile[/]",
        border_style="yellow"
    )

    # Smart Tips
    tips_str = "\n".join([f"💡 {Markup.escape(t)}" for t in profile.get('smart_tips', [])])
    tips_panel = Panel(tips_str, title="[bold white]Actionable Advice[/]", border_style="white")

    console.print(Align.center(title))
    console.print(summary_panel)
    console.print(focus_panel)
    console.print(psyche_panel)
    console.print(tips_panel)

@app.command("ai-add")
def ai_add(prompt: list[str] = typer.Argument(..., help="Natural language description of the task")):
    """Add a task using natural language (Gemini)."""
    try:
        check_and_run_gap_recovery()
        prompt_str = " ".join(prompt)
        try:
            user_profile_json = trigger_ai_study()
            with console.status("[bold blue]AI parsing task...[/]"):
                data = smart_parse_task(prompt_str, user_profile_json=user_profile_json)
        except AIApiError as e:
            console.print(f"\n[bold red]🧠 AI Service Error:[/] {e}")
            return

        if not data:

            console.print("[red]AI parsing failed. Check your API key.[/]")
            return

        # Pretty Preview Card
        preview_table = RichTable(show_header=False, box=box.SIMPLE_HEAD)
        preview_table.add_column("Field", style="bold cyan")
        preview_table.add_column("Value")
        preview_table.add_row("Title", data.get('title'))
        preview_table.add_row("Description", data.get('description', 'N/A'))
        preview_table.add_row("Status", data.get('status', 'TODO'))
        preview_table.add_row("Progress", f"{data.get('progress', 0)}%")
        preview_table.add_row("Tags", data.get('tags', 'None'))
        preview_table.add_row("Due Date", data.get('due_date', 'None'))
        
        console.print(Panel(preview_table, title="[bold green]AI Suggestion Preview[/]", border_style="green"))

        confirmed = True
        if os.environ.get("FLOWLOG_TUI_MODE") != "1":
            confirmed = typer.confirm("Confirm and add this task?", default=True)
            
        if confirmed:
            tags_value = data.get('tags','')
            if not tags_value:
                tags_list = infer_tags_local(data.get('description',''))
                tags_value = ",".join(tags_list)
            new_id = add_log(data['title'], data.get('description',''), data.get('status','TODO'), 
                    data.get('progress',0), tags_value, data.get('due_date','None'))
            console.print(f"[green]Task added successfully! (ID: {new_id})[/]")
            console.print(f"[dim]To revert, use 'delete {new_id}'[/]")
    except Exception as e:
        console.print(f"[red]Error in ai-add: {e}[/]")
        console.print("[dim]Check your API key and try again.[/]")

@app.command("ai-summary")
def ai_summary():
    """AI-powered productivity analysis and motivation."""
    try:
        user_profile_json = trigger_ai_study()
    except AIApiError as e:
        console.print(f"\n[bold red]🧠 AI Service Error:[/] {e}")
        return
        
    from db import get_last_log_date

    last_event_date = get_last_log_date()
    time_context = get_real_time_context(last_event_date)

    conn = get_db_connection()
    cursor = conn.cursor()
    # Use log_date for logical chronological ordering
    cursor.execute("SELECT title, status, progress, tags, updated_at, log_date FROM logs ORDER BY log_date DESC, id DESC LIMIT 20")
    logs = [dict(row) for row in cursor.fetchall()]
    conn.close()

    if not logs:
        console.print("[yellow]Not enough data for AI analysis.[/]")
        return

    with console.status("[bold magenta]AI analyzing your patterns...[/]"):
        try:
            report = generate_ai_summary(logs, user_profile_json=user_profile_json, time_context=time_context)
        except AIApiError as e:
            console.print(f"\n[bold red]🧠 AI Service Error:[/] {e}")
            return


    from rich.text import Text
    console.print(Panel(Text(report), title="[BRAIN] AI Productivity Insights", border_style="cyan"))

@app.command("ai-rehydrate")
def ai_rehydrate():
    """Convert 'Gap summary' entries into detailed multi-entry logs when AI becomes available."""
    with console.status("[bold blue]Rehydrating gap summaries...[/]"):
        count = rehydrate_gap_summaries()
    if count:
        console.print(f"[green]Rehydrated {count} gap summaries into detailed logs.[/]")
    else:
        console.print("[yellow]No gap summaries found to rehydrate.[/]")

@app.command("view-logs")
def view_logs(page: int = typer.Option(1), page_size: int = typer.Option(15), mode: str = typer.Option("compact"), details: bool = typer.Option(False)):
    """Static view of logs (classic style)."""
    rows = get_all_logs_with_tags()
    entries = []
    for r in rows:
        entries.append({
            "id": r["id"],
            "title": r["title"],
            "description": r["description"],
            "status": r["status"],
            "progress": r["progress"],
            "created_at": r["created_at"],
            "tags": r["tags"].split(",") if r["tags"] else []
        })
    console.print(grouped_logs_table(entries, page=page, page_size=page_size, mode=mode, show_details=details))

# --- Import / Export ---

@app.command()
def export_logs(filename: str):
    """Export all logs to JSON or CSV."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM logs")
    rows = cursor.fetchall()
    cols = [d[0] for d in cursor.description]
    conn.close()
    data = [dict(zip(cols, r)) for r in rows]

    if filename.endswith(".json"):
        with open(filename, "w") as f: json.dump(data, f, indent=4)
    elif filename.endswith(".csv"):
        with open(filename, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader(); w.writerows(data)
    console.print(f"[green]Exported to {filename}[/]")

@app.command()
def import_logs(filename: str):
    """Import logs from JSON or CSV."""
    if not os.path.exists(filename):
        console.print("[red]File not found.[/]")
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    if filename.endswith(".json"):
        with open(filename, "r") as f: data = json.load(f)
        for item in data:
            cursor.execute("INSERT INTO logs (title, description, status, progress, tags, due_date) VALUES (?,?,?,?,?,?)",
                           (item['title'], item.get('description',''), item.get('status','TODO'), 
                            item.get('progress',0), item.get('tags',''), item.get('due_date','None')))
    elif filename.endswith(".csv"):
        with open(filename, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                cursor.execute("INSERT INTO logs (title, description, status, progress, tags, due_date) VALUES (?,?,?,?,?,?)",
                               (row['title'], row.get('description',''), row.get('status','TODO'), 
                                int(row.get('progress',0)), row.get('tags',''), row.get('due_date','None')))
    conn.commit()
    conn.close()
    console.print("[green]Import complete![/]")

# --- Tag Management ---

@app.command("add-tag")
def add_tag_cmd(log_id: int, tags: str):
    """Add tags to a task."""
    row = get_log_by_id(log_id)
    if not row: return
    existing = row[7].split(",") if row[7] else []
    new = [t.strip() for t in tags.split(",") if t.strip()]
    updated = list(set(existing + new))
    update_tags(log_id, updated)
    console.print(f"[green]Tags updated for {log_id}.[/]")

if __name__ == "__main__":
    app()
