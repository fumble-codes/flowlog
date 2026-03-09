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
from rich.console import Console
from rich.panel import Panel
from rich.align import Align
from rich.table import box
from rich.progress import Progress, BarColumn, TextColumn, TaskProgressColumn

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
    get_real_time_context
)

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
        logs = [dict(row) for row in get_all_logs_with_tags()]
        if logs:
            new_profile = study_user_patterns(logs)
            if new_profile:
                update_ai_memory("user_profile", new_profile)
                return new_profile
    return profile

# App Setup
app = typer.Typer(help="Flowlog: A modern CLI project tracker with AI insights.")
console = Console()

# Ensure DB directory exists
APP_NAME = "Flowlog"
APP_DIR = Path(os.environ.get("APPDATA", Path.home())) / APP_NAME
APP_DIR.mkdir(parents=True, exist_ok=True)
DB_NAME = str(APP_DIR / "flowlog.db")

# Initialize DB on start
init_db()

# --- Callbacks ---
@app.callback(invoke_without_command=True)
def _default(ctx: typer.Context):
    if ctx.invoked_subcommand is None:
        home()

# --- Core Commands ---

@app.command()
def hello():
    """Welcome message."""
    console.print("[bold green]Welcome to Flowlog - Your AI-Powered Progress Tracker![/]")

@app.command("home")
def home():
    """Flowlog Command Center Dashboard."""
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
        due_table.add_column("Progress", width=20)
        due_table.add_column("Due", style="red")

        for idx, row in enumerate(due_today, start=1):
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
        due_str = row[6]
        if due_str and due_str != "None":
            try:
                due_date_obj = datetime.strptime(due_str[:10], "%Y-%m-%d").date()
                if due_date_obj > today:
                    upcoming.append((due_date_obj, row))
            except ValueError: pass

    upcoming.sort(key=lambda x: x[0])
    nearest = upcoming[:5]

    urgent_table = Table(title="[bold red]Urgent Tasks • Nearest Due Dates[/]")
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

    tips = "[italic dim]Tips:[/] [bold]ai-add[/] \"task\" • [bold]ai-summary[/] • [bold]insights[/] • [bold]dashboard[/] • [bold]search[/] query"
    console.print(Panel.fit(tips, box=box.ASCII2))
    console.print(Align.center(f"[dim]Flowlog • {datetime.now().strftime('%Y-%m-%d %H:%M')}[/dim]"))

@app.command()
def add():
    """Add a new progress log manually."""
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
        add_log(title, description, status, progress, tags, due_date)
        console.print(f"[green]Log added successfully![/]")
    except Exception as e:
        console.print(f"[red]Failed to save log: {e}[/]")

@app.command()
def view(td: bool = typer.Option(False, "--td", help="Show only today's logs")):
    """View logs in a formatted table."""
    if td:
        today_str = datetime.now().date().isoformat()
        logs = get_logs_by_due_date(today_str)
    else:
        logs = get_all_logs_with_due()

    if not logs:
        console.print("[bold yellow]No logs found.[/]")
        return

    table = Table(title="All Logs")
    table.add_column("ID", style="dim", width=6)
    table.add_column("Title", style="bold")
    table.add_column("Status", style="cyan")
    table.add_column("Progress", width=20)
    table.add_column("Due Date", style="red")

    for log in logs:
        log_id, title, desc, status, progress, tags, due_date = log
        table.add_row(str(log_id), title, status, render_progress(progress), due_date or "")

    console.print(table)

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
        title = typer.prompt("New title?", default=row[1])
        desc = typer.prompt("New description?", default=row[2])
        status = typer.prompt("New status?", default=row[3]).upper()
        progress_str = typer.prompt("New progress?", default=str(row[4]))
        progress = int(progress_str)

    update_log(log_id, title, desc, status, progress)
    console.print(f"[green]Log {log_id} updated![/]")

@app.command()
def delete(log_id: int):
    """Delete a log."""
    if delete_log(log_id):
        console.print(f"[green]Deleted log {log_id}.[/]")
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

# --- View & Search Commands ---

@app.command()
def search(query: str):
    """Search tasks by title, description or tags."""
    conn = get_db_connection()
    cursor = conn.cursor()
    q = f"%{query}%"
    cursor.execute("SELECT * FROM logs WHERE title LIKE ? OR description LIKE ? OR tags LIKE ?", (q, q, q))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        console.print(f"[yellow]No results for '{query}'.[/]")
        return

    table = Table(title=f"Search Results: {query}")
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
    panel = Panel(
        Align.center(
            f"Total: {total} | TODO: {counts.get('TODO',0)} | WIP: {counts.get('WIP',0)} | DONE: {done}\n\n"
            f"Completion: {render_progress(int(rate))} [green]{rate:.1f}%[/]"
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
    user_profile_json = trigger_ai_study()
    if not user_profile_json:
        console.print("[bold yellow]Not enough data to generate insights yet. Keep logging![/]")
        return

    try:
        profile = json.loads(user_profile_json)
    except Exception as e:
        console.print(f"[red]Error parsing user profile: {e}[/]")
        return

    # Create a rich layout for insights
    title = f"[bold magenta]🧠 Deep Productivity Insights[/]"
    
    # Archetypes as badges
    archetypes_str = " ".join([f"[bold cyan on blue] {a} [/]" for a in profile.get('archetypes', [])])
    
    # Summary panel
    summary_panel = Panel(
        f"{profile.get('summary', 'No summary available.')}\n\n"
        f"[bold cyan]Archetypes:[/] {archetypes_str}\n"
        f"[bold cyan]Working Hours:[/] {profile.get('working_hours', 'Unknown')}",
        title="[bold blue]Overview[/]",
        border_style="blue"
    )

    # Focus breakdown
    focus_str = "\n".join([f"- {f}" for f in profile.get('focus_breakdown', [])])
    focus_panel = Panel(focus_str, title="[bold green]Focus Breakdown[/]", border_style="green")

    # Psychological Profile
    psyche_panel = Panel(
        f"{profile.get('psychological_profile', 'No analysis available.')}",
        title="[bold yellow]Psychological Profile[/]",
        border_style="yellow"
    )

    # Smart Tips
    tips_str = "\n".join([f"💡 {t}" for t in profile.get('smart_tips', [])])
    tips_panel = Panel(tips_str, title="[bold white]Actionable Advice[/]", border_style="white")

    console.print(Align.center(title))
    console.print(summary_panel)
    console.print(focus_panel)
    console.print(psyche_panel)
    console.print(tips_panel)

@app.command("ai-add")
def ai_add(prompt: str):
    """Add a task using natural language (Gemini)."""
    user_profile_json = trigger_ai_study()
    with console.status("[bold blue]AI parsing task...[/]"):
        data = smart_parse_task(prompt, user_profile_json=user_profile_json)

    if not data:
        console.print("[red]AI parsing failed. Check your API key.[/]")
        return

    console.print(Panel(json.dumps(data, indent=2), title="AI Suggestion"))
    if typer.confirm("Add this task?", default=True):
        add_log(data['title'], data.get('description',''), data.get('status','TODO'), 
                data.get('progress',0), data.get('tags',''), data.get('due_date','None'))
        console.print("[green]Added![/]")

@app.command("ai-summary")
def ai_summary():
    """AI-powered productivity analysis and motivation."""
    user_profile_json = trigger_ai_study()
    from db import get_last_log_time
    last_log_time = get_last_log_time()
    time_context = get_real_time_context(last_log_time)

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT title, status, progress, tags, updated_at FROM logs ORDER BY updated_at DESC LIMIT 20")
    logs = [dict(row) for row in cursor.fetchall()]
    conn.close()

    if not logs:
        console.print("[yellow]Not enough data for AI analysis.[/]")
        return

    with console.status("[bold magenta]AI analyzing your patterns...[/]"):
        report = generate_ai_summary(logs, user_profile_json=user_profile_json, time_context=time_context)

    console.print(Panel(report, title="🧠 AI Productivity Insights", border_style="cyan"))

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

# --- Interactive Shell ---

def interactive_shell():
    console.clear()
    trigger_ai_study()
    home()
    while True:
        try:
            cmd = input("\n[Flowlog] > ").strip()
            if cmd.lower() in ["exit", "quit"]: break
            if cmd:
                args = shlex.split(cmd)
                try: app(args)
                except SystemExit: pass
                if args[0].lower() in {"add", "delete", "update", "ai-add"}:
                    console.print("\nRefreshed Dashboard...")
                    home()
        except KeyboardInterrupt: break
        except Exception as e: console.print(f"[red]Error: {e}[/]")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        app()
    else:
        interactive_shell()
