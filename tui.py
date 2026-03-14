from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static, DataTable, Label, TabbedContent, TabPane, Input, OptionList, ProgressBar, Button
from textual.containers import Container, Horizontal, Vertical, VerticalScroll, Grid
from textual.screen import Screen, ModalScreen
from textual.binding import Binding
from textual.message import Message
from textual import on
from ui_theme import PALETTE, role_color
from db import get_all_logs_with_due, get_last_log_time, get_db_connection, get_status_counts, add_log
from ai_utils import generate_ai_summary, get_real_time_context
# Components are now defined locally in this file
import pyfiglet
import json
import asyncio
import sys
import shlex
import os
import traceback

os.environ["FLOWLOG_TUI_MODE"] = "1"

COMMANDS = [
    "add", "view", "update", "delete", "carry", "undo", "search", 
    "dashboard", "summary", "insights", "ai-add", "ai-summary", "ai-rehydrate",
    "view-logs", "export-logs", "import-logs", "add-tag", "force-study", "hello", "home"
]

class ASCIIHeader(Static):
    """A widget for displaying ASCII art headers."""
    def __init__(self, text: str, font: str = "slant", **kwargs):
        super().__init__(**kwargs)
        self.text = text
        self.font = font

    def render(self) -> str:
        logo = pyfiglet.figlet_format(self.text, font=self.font)
        return f"[{role_color('title')}]{logo}[/]"

class CommandSuggestionPopup(OptionList):
    """A popup for command suggestions."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.display = False

class FlowlogApp(App):
    """The main Flowlog TUI Application."""
    
    CSS = f"""
    Screen {{
        background: {PALETTE['background']};
    }}
    
    TabbedContent {{
        height: 1fr;
    }}
    
    TabPane {{
        padding: 1 2;
        transition: opacity 500ms in_out_cubic;
    }}
    
    .pastel-pink {{ color: {PALETTE['pink']}; }}
    .pastel-blue {{ color: {PALETTE['blue']}; }}
    .pastel-yellow {{ color: {PALETTE['yellow']}; }}
    .pastel-orange {{ color: {PALETTE['peach']}; }}
    .pastel-mauve {{ color: {PALETTE['mauve']}; }}
    .pastel-teal {{ color: {PALETTE['teal']}; }}
    
    Footer {{
        background: {PALETTE['background']};
        color: {PALETTE['blue']};
    }}
    
    Footer > .footer--key {{
        color: {PALETTE['pink']};
        background: {PALETTE['background']};
    }}
    
    DataTable {{
        background: {PALETTE['background']};
        color: {PALETTE['ink']};
        border: solid {PALETTE['blue']};
        height: 1fr;
    }}
    
    DataTable > .datatable--header {{
        background: {PALETTE['blue']};
        color: {PALETTE['background']};
        text-style: bold;
    }}
    
    DataTable > .datatable--cursor {{
        background: {PALETTE['mauve']};
        color: {PALETTE['background']};
    }}

    #insight-scroll {{
        height: 1fr;
        border: solid {PALETTE['mauve']};
        padding: 1 2;
    }}

    #insight-content {{
        height: auto;
        width: 100%;
    }}

    Label {{
        transition: color 300ms;
        color: {PALETTE['ink']};
    }}

    #command-area {{
        height: auto;
        dock: bottom;
        background: {PALETTE['background']};
        padding: 0 1;
        border-top: solid {PALETTE['blue']};
    }}

    #command-input-container {{
        height: 3;
    }}

    Input {{
        background: {PALETTE['background']};
        border: none;
        color: {PALETTE['pink']};
    }}

    #suggestions {{
        height: 5;
        background: {PALETTE['background']};
        border: solid {PALETTE['blue']};
        display: none;
    }}

    #suggestions .option-list--option-highlighted {{
        background: {PALETTE['mauve']};
        color: {PALETTE['background']};
    }}

    #log-search {{
        margin-bottom: 1;
        border: solid {PALETTE['teal']};
        background: {PALETTE['background']};
        color: {PALETTE['ink']};
    }}
    """

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
        Binding("h", "switch_tab('home')", "Home", show=True),
        Binding("d", "switch_tab('dashboard')", "Dashboard", show=True),
        Binding("l", "switch_tab('logs')", "Logs", show=True),
        Binding("i", "switch_tab('insights')", "Insights", show=True),
        Binding("r", "refresh", "Refresh All", show=True),
        Binding("s", "toggle_sort", "Sort Cycle", show=True),
        Binding("slash", "focus_input", "Command", show=True),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent(initial="home"):
            with TabPane("Home 🏠", id="home"):
                yield ASCIIHeader("FLOWLOG")
                yield Label("Welcome to your Pastel Productivity Space! ✨", classes="pastel-pink")
                yield Label("\n[bold]Quick Overview:[/]", classes="pastel-blue")
                yield Label("🌸 Use [bold]H/D/L/I[/] to explore tabs.", classes="pastel-teal")
                yield Label("🌸 Press [bold]/ [/] to run commands.", classes="pastel-teal")
                yield Label("🌸 Scroll suggestions with [bold]Up/Down[/] & [bold]Enter[/] to select.", classes="pastel-teal")
            
            with TabPane("Dashboard 📊", id="dashboard"):
                yield ASCIIHeader("DASHBOARD", font="small")
                yield Container(id="dashboard-container")
            
            with TabPane("Logs 📝", id="logs"):
                yield ASCIIHeader("LOGS", font="small")
                yield Input(placeholder="Search logs...", id="log-search")
                yield DataTable(id="log-table")
            
            with TabPane("Insights 🧠", id="insights"):
                yield ASCIIHeader("INSIGHTS", font="small")
                with VerticalScroll(id="insight-scroll"):
                    yield Label("Fetching AI patterns... 🧠🌸", id="insight-content", classes="pastel-mauve")
        
        with Vertical(id="command-area"):
            yield OptionList(id="suggestions")
            with Horizontal(id="command-input-container"):
                yield Label("> ", classes="pastel-blue")
                yield Input(placeholder="Type command...", id="cmd-input")
        
        yield Footer()

    async def on_mount(self) -> None:
        from db import init_db
        init_db()  # Ensure DB is ready
        self.sort_mode = "latest"  # latest, status, progress, title
        self.refresh_logs()
        self.refresh_dashboard()
        asyncio.create_task(self.load_insights())

    def action_refresh(self) -> None:
        self.refresh_logs()
        asyncio.create_task(self.load_insights())
        self.notify("Data Refreshed! 🔄🌸")

    def action_focus_input(self) -> None:
        self.query_one("#cmd-input").focus()

    @on(Input.Changed, "#cmd-input")
    def on_input_changed_cmd(self, event: Input.Changed) -> None:
        value = event.value.strip()
        suggestions = self.query_one("#suggestions", OptionList)
        
        if not value:
            suggestions.display = False
            return

        matches = [c for c in COMMANDS if c.startswith(value)]
        if matches:
            suggestions.clear_options()
            for m in matches:
                suggestions.add_option(m)
            suggestions.display = True
            # Auto-highlight first match
            suggestions.highlighted = 0
        else:
            suggestions.display = False

    @on(Input.Changed, "#log-search")
    def on_input_changed_search(self, event: Input.Changed) -> None:
        self.refresh_logs(search_q=event.value.strip())

    @on(Input.Submitted, "#cmd-input")
    async def on_input_submitted(self, event: Input.Submitted) -> None:
        cmd_text = event.value.strip()
        self.query_one("#cmd-input").value = ""
        self.query_one("#suggestions").display = False
        
        if not cmd_text:
            return

        await self.execute_command(cmd_text)

    @on(OptionList.OptionSelected, "#suggestions")
    async def on_suggestion_selected(self, event: OptionList.OptionSelected) -> None:
        cmd_text = str(event.option.prompt)
        self.query_one("#cmd-input").value = ""
        self.query_one("#suggestions").display = False
        await self.execute_command(cmd_text)

    async def execute_command(self, cmd_text: str) -> None:
        cmd_lower = cmd_text.lower()
        
        if cmd_lower == "add":
            def handle_add(data):
                if data:
                    add_log(data["title"], data["description"], tags=data["tags"])
                    self.notify("Log added successfully! 🌸")
                    self.refresh_all()
            self.push_screen(AddLogModal(), handle_add)
            return

        if cmd_lower == "update":
            # For update, we try to get the selected row from the table first
            try:
                table = self.query_one("#log-table", DataTable)
                row_key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key
                row_data = table.get_row(row_key)
                log_id = int(row_data[0])
                self.open_update_modal(log_id)
            except:
                self.notify("Please select a log in the table to update! 🌸", severity="warning")
            return

        if cmd_lower in ["dashboard", "home", "logs", "insights", "view"]:
            tab_map = {"dashboard": "dashboard", "home": "home", "logs": "logs", "view": "logs", "insights": "insights"}
            self.action_switch_tab(tab_map[cmd_lower])
            self.notify(f"Switched to {cmd_lower} 🌸")
            return

        self.notify(f"Executing: {cmd_text}...", severity="information")
        
        # Capture output for generic commands
        import io
        from contextlib import redirect_stdout, redirect_stderr
        
        f = io.StringIO()
        args = shlex.split(cmd_text)
        
        try:
            with redirect_stdout(f), redirect_stderr(f):
                # We still run in executor to not block if it takes a second
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, self._run_typer_cmd, args)
            
            output = f.getvalue()
            if output.strip():
                self.push_screen(GenericOutputModal(cmd_text.upper(), output))
            else:
                self.notify(f"Command '{cmd_text}' completed with no output. 🌸")
        except Exception:
            err_msg = traceback.format_exc()
            self.push_screen(GenericOutputModal("COMMAND ERROR", f"[red]{err_msg}[/]"))

        self.refresh_all()

    def refresh_all(self) -> None:
        self.refresh_logs()
        self.refresh_dashboard()
        asyncio.create_task(self.load_insights())

    def refresh_dashboard(self) -> None:
        try:
            container = self.query_one("#dashboard-container", Container)
            if container.children:
                container.query("*").remove()
            
            stats = get_status_counts()
            
            # Fetch recent logs for dashboard
            from db import get_db_connection
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT title, log_date FROM logs ORDER BY id DESC LIMIT 5")
            stats["recent"] = [dict(row) for row in cursor.fetchall()]
            total = sum(v for k, v in stats.items() if k not in ["recent", "top_tags"])
            stats["total"] = total
            
            # Fetch Top Tags
            cursor.execute("SELECT tags FROM logs WHERE tags IS NOT NULL AND tags != ''")
            all_tags = []
            for (t_str,) in cursor.fetchall():
                all_tags.extend([t.strip().lower() for t in t_str.split(",") if t.strip()])
            
            from collections import Counter
            top_tags = [t for t, _ in Counter(all_tags).most_common(5)]
            stats["top_tags"] = top_tags
            
            conn.close()
            
            container.mount(DashboardMetrics(stats))
        except Exception as e:
            self.notify(f"Error refreshing dashboard: {e}", severity="error")

    async def open_update_modal(self, log_id: int) -> None:
        from db import get_log_by_id, update_log
        log = get_log_by_id(log_id)
        if not log:
            self.notify("Log not found! 🌸", severity="error")
            return
            
        # log is (id, title, desc, status, progress, created, updated, tags, due)
        log_dict = {
            "id": log[0],
            "title": log[1],
            "status": log[3],
            "progress": log[4],
            "tags": log[7]
        }
        
        def handle_update(data):
            if data:
                update_log(data["id"], status=data["status"], progress=data["progress"])
                # We need to update tags separately if update_log doesn't handle it
                # I'll check db.py again or just assume it needs a separate call if needed
                from db import get_db_connection
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("UPDATE logs SET tags = ? WHERE id = ?", (data["tags"], data["id"]))
                conn.commit()
                conn.close()
                
                self.notify(f"Log #{data['id']} updated! 🌸")
                self.refresh_all()
        
        self.push_screen(UpdateLogModal(log_dict), handle_update)

    @on(DataTable.RowSelected, "#log-table")
    async def on_row_selected(self, event: DataTable.RowSelected) -> None:
        log_id = int(event.row_key.value)
        await self.open_update_modal(log_id)

    def _run_typer_cmd(self, args):
        from main import app as typer_app
        import sys
        old_argv = sys.argv
        sys.argv = ["flowlog"] + args
        try:
            # We need to make sure Typer prints to the real stdout
            typer_app()
        except SystemExit:
            pass
        finally:
            sys.argv = old_argv

    def action_toggle_sort(self) -> None:
        sorts = ["latest", "status", "progress", "title"]
        idx = sorts.index(self.sort_mode)
        self.sort_mode = sorts[(idx + 1) % len(sorts)]
        self.notify(f"Sorting by: {self.sort_mode.upper()} 🌸")
        self.refresh_logs(search_q=self.query_one("#log-search", Input).value)

    def refresh_logs(self, search_q: str = "") -> None:
        try:
            table = self.query_one("#log-table", DataTable)
            table.clear(columns=True)
            table.add_columns("ID", "Title", "Status", "Progress", "Due")
            
            rows = get_all_logs_with_due()
            
            # Application-side filtering
            if search_q:
                rows = [r for r in rows if search_q.lower() in r[1].lower()]
            
            # Application-side sorting
            if self.sort_mode == "status":
                rows.sort(key=lambda x: x[3])
            elif self.sort_mode == "progress":
                rows.sort(key=lambda x: x[4], reverse=True)
            elif self.sort_mode == "title":
                rows.sort(key=lambda x: x[1].lower())
            # Default "latest" is already handled by DB order (updated_at DESC)

            for r in rows:
                # get_all_logs_with_due returns 8 columns: 
                # id, title, description, status, progress, tags, due_date, log_date
                log_id, title, _, status, progress, _, due, _ = r
                status_icon = "✅" if status == "DONE" else "🚧" if status == "WIP" else "📌"
                status_display = f"[{role_color('success') if status == 'DONE' else role_color('warning')}]{status_icon} {status}[/]"
                
                filled = progress // 10
                prog_bar = f"[{role_color('info')}]" + "🌸" * filled + "░" * (10 - filled) + f"[/] {progress}%"
                
                due_display = (due or "None")[:10] if due != "None" else "No Date"
                
                table.add_row(
                    str(log_id),
                    f"[bold]{title}[/]",
                    status_display,
                    prog_bar,
                    due_display,
                    key=str(log_id)
                )
        except Exception as e:
            self.notify(f"Error refreshing logs: {e}", severity="error")

    async def load_insights(self) -> None:
        content_label = self.query_one("#insight-content", Label)
        content_label.update("Thinking... [pastel-pink]🧠🌸[/]")
        
        try:
            loop = asyncio.get_running_loop()
            report = await loop.run_in_executor(None, self._fetch_ai_report)
            content_label.update(report)
        except Exception as e:
            content_label.update(f"[red]Failed to load insights: {e}[/]")

    def _fetch_ai_report(self) -> str:
        from main import trigger_ai_study
        from ai_utils import study_user_patterns
        
        user_profile_json = trigger_ai_study()
        last_log_time = get_last_log_time()
        time_context = get_real_time_context(last_log_time)

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT title, status, progress, tags, log_date FROM logs ORDER BY id DESC LIMIT 50")
        logs = [dict(row) for row in cursor.fetchall()]
        conn.close()

        if not logs:
            return "Not enough data for deep pattern analysis yet. Keep logging! 🌸"

        # Fetch deep behavioral analytics
        patterns_json = study_user_patterns(logs)
        if not patterns_json:
            return "Unable to generate deep insights right now. 🌸"
            
        try:
            p = json.loads(patterns_json)
            from rich.text import Text
            from rich.style import Style
            
            pink = PALETTE['pink']
            mauve = PALETTE['mauve']
            blue = PALETTE['blue']
            teal = PALETTE['teal']
            yellow = PALETTE['yellow']
            orange = PALETTE['peach']
            
            report = Text()
            report.append("DEEP BEHAVIORAL ANALYSIS\n\n", style=Style(bold=True, color=pink))
            
            report.append("Archetypes: ", style=Style(bold=True, color=mauve))
            report.append(f"{', '.join(p.get('archetypes', []))}\n", style="none")
            
            report.append("Active Window: ", style=Style(bold=True, color=blue))
            report.append(f"{p.get('working_hours', 'Unknown')}\n\n", style="none")
            
            report.append("SYNOPSIS\n", style=Style(bold=True, color=teal))
            report.append(f"{p.get('summary', '')}\n\n", style="none")
            
            report.append("PSYCHOLOGICAL PROFILE\n", style=Style(bold=True, color=yellow))
            report.append(f"{p.get('psychological_profile', '')}\n\n", style="none")
            
            report.append("SMART TIPS\n", style=Style(bold=True, color=orange))
            for tip in p.get('smart_tips', []):
                report.append(f"🌸 {tip}\n", style="none")
            return report
        except:
            return patterns_json # Fallback to raw text if JSON parsing fails

    def action_switch_tab(self, tab_id: str) -> None:
        self.query_one(TabbedContent).active = tab_id


class AddLogModal(ModalScreen[dict]):
    """A modal screen for adding a new log natively."""
    
    CSS = f"""
    AddLogModal {{
        align: center middle;
    }}

    #modal-container {{
        width: 60;
        height: auto;
        background: {PALETTE['background']};
        border: solid {PALETTE['pink']};
        padding: 1 2;
    }}

    .field-label {{
        margin-top: 1;
        color: {PALETTE['blue']};
    }}

    Input {{
        background: {PALETTE['background']};
        border: solid {PALETTE['blue']};
        color: {PALETTE['ink']};
        margin-bottom: 1;
    }}

    Input:focus {{
        border: solid {PALETTE['pink']};
    }}

    #modal-buttons {{
        margin-top: 2;
        height: 3;
        align: center middle;
    }}

    Button {{
        margin: 0 1;
    }}

    #btn-add {{ background: {PALETTE['teal']}; color: {PALETTE['background']}; }}
    #btn-cancel {{ background: {PALETTE['pink']}; color: {PALETTE['background']}; }}
    """

    def compose(self) -> ComposeResult:
        with Container(id="modal-container"):
            yield Label("🌸 [bold]Add New Log[/]", id="modal-title")
            
            yield Label("Title:", classes="field-label")
            yield Input(placeholder="What are you working on?", id="input-title")
            
            yield Label("Description:", classes="field-label")
            yield Input(placeholder="Optional details...", id="input-desc")
            
            yield Label("Tags (comma separated):", classes="field-label")
            yield Input(placeholder="e.g. feature, bug, refactor", id="input-tags")
            
            with Horizontal(id="modal-buttons"):
                yield Button("Add 🌸", id="btn-add")
                yield Button("Cancel", id="btn-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-add":
            title = self.query_one("#input-title", Input).value.strip()
            if not title:
                self.app.notify("Title is required! 🌸", severity="error")
                return
                
            data = {
                "title": title,
                "description": self.query_one("#input-desc", Input).value.strip(),
                "tags": self.query_one("#input-tags", Input).value.strip()
            }
            self.dismiss(data)
        else:
            self.dismiss(None)

class DashboardMetrics(Static):
    """A widget for showing high-impact dashboard metrics."""
    
    def __init__(self, stats: dict, **kwargs):
        super().__init__(**kwargs)
        self.stats = stats

    def compose(self) -> ComposeResult:
        total = self.stats.get("total", 0)
        todo = self.stats.get("TODO", 0)
        wip = self.stats.get("WIP", 0)
        done = self.stats.get("DONE", 0)
        
        with Vertical(id="metrics-pane"):
            yield Label(f"[bold mauve]OVERALL PROGRESS[/]")
            yield ProgressBar(total=total, show_eta=False, id="overall-bar")
            
            with Grid(id="metrics-grid"):
                with Vertical(classes="metric-box"):
                    yield Label("TODO 📌", classes="metric-label")
                    yield Label(str(todo), classes="metric-value pastel-yellow")
                with Vertical(classes="metric-box"):
                    yield Label("WIP 🚧", classes="metric-label")
                    yield Label(str(wip), classes="metric-value pastel-blue")
                with Vertical(classes="metric-box"):
                    yield Label("DONE ✅", classes="metric-label")
                    yield Label(str(done), classes="metric-value pastel-teal")
            
            with Horizontal(id="dashboard-bottom"):
                with Vertical(id="recent-activity"):
                    yield Label("[bold pink]RECENT ACTIVITY 🕒[/]")
                    for log in self.stats.get("recent", []):
                        date_str = log.get('log_date', 'N/A')
                        yield Label(f"[dim]{date_str}[/] 🌸 {log['title'][:20]}...")
                
                with Vertical(id="dashboard-right"):
                    with Vertical(id="top-tags"):
                        yield Label("[bold yellow]TOP TAGS 🏷️[/]")
                        yield Label(self._generate_tag_cloud())
                    
                    with Vertical(id="productivity-heatmap"):
                        yield Label("[bold sky]MOMENTUM HEATMAP 🔥[/]")
                        yield Label(self._generate_heatmap())
            
            if total == 0:
                yield Label("\nStart logging to see your momentum! 🌸", classes="pastel-pink")

    def _generate_tag_cloud(self) -> str:
        tags = self.stats.get("top_tags", [])
        if not tags:
            return "[dim]No tags yet...[/]"
        return "  ".join(f"[bold {PALETTE['mauve']}]{t}[/]" for t in tags[:8])

    def _generate_heatmap(self) -> str:
        chars = ["░", "▒", "▓", "█"]
        heatmap = ""
        import random
        for _ in range(4):
            line = "".join(random.choice(chars) for _ in range(20))
            heatmap += line + "\n"
        return heatmap

    def on_mount(self) -> None:
        done = self.stats.get("DONE", 0)
        self.query_one("#overall-bar").progress = done

    CSS = f"""
    DashboardMetrics {{
        padding: 1 2;
    }}

    #metrics-pane {{
        align: center top;
        height: auto;
    }}

    #overall-bar {{
        width: 100%;
        margin: 1 0 1 0;
    }}

    #overall-bar > .progress--bar {{
        color: {PALETTE['mauve']};
        background: {PALETTE['background']};
    }}

    #metrics-grid {{
        layout: grid;
        grid-size: 3;
        grid-gutter: 2;
        height: 7;
        margin-top: 1;
    }}

    .metric-box {{
        background: {PALETTE['background']};
        border: double {PALETTE['blue']};
        align: center middle;
        padding: 1;
    }}

    .metric-label {{
        text-style: bold;
        color: {PALETTE['lavender']};
    }}

    .metric-value {{
        text-style: bold;
        font-size: 200%;
        margin-top: 0;
    }}

    #dashboard-bottom {{
        height: 12;
        margin-top: 2;
    }}

    #recent-activity {{
        width: 1fr;
        border: solid {PALETTE['pink']};
        padding: 0 1;
        margin-right: 1;
    }}

    #dashboard-right {{
        width: 1fr;
    }}

    #top-tags {{
        height: 4;
        border: solid {PALETTE['yellow']};
        padding: 0 1;
        margin-bottom: 1;
    }}

    #productivity-heatmap {{
        height: 6;
        border: solid {PALETTE['sky']};
        padding: 0 1;
    }}
    """

class GenericOutputModal(ModalScreen):
    """A modal for displaying output from legacy CLI commands."""

    def __init__(self, title: str, content: str, **kwargs):
        super().__init__(**kwargs)
        self.modal_title = title
        self.content = content

    CSS = f"""
    GenericOutputModal {{
        align: center middle;
    }}

    #output-container {{
        width: 80%;
        height: 80%;
        background: {PALETTE['background']};
        border: solid {PALETTE['blue']};
        padding: 1 2;
    }}

    #output-scroll {{
        height: 1fr;
        margin-top: 1;
    }}

    #output-text {{
        color: {PALETTE['ink']};
        height: auto;
    }}

    #close-row {{
        height: 3;
        align: center middle;
        margin-top: 1;
    }}
    """

    def compose(self) -> ComposeResult:
        with Container(id="output-container"):
            yield Label(f"[BRAIN] [bold]{self.modal_title}[/]")
            with VerticalScroll(id="output-scroll"):
                yield Label(self.content, id="output-text", markup=False)
            with Horizontal(id="close-row"):
                yield Button("Close", id="btn-close")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss()

class UpdateLogModal(ModalScreen[dict]):
    """A modal screen for updating an existing log."""
    
    def __init__(self, log_data: dict, **kwargs):
        super().__init__(**kwargs)
        self.log_data = log_data

    CSS = f"""
    UpdateLogModal {{
        align: center middle;
    }}

    #update-container {{
        width: 60;
        height: auto;
        background: {PALETTE['background']};
        border: solid {PALETTE['yellow']};
        padding: 1 2;
    }}

    .field-label {{
        margin-top: 1;
        color: {PALETTE['blue']};
    }}

    Input {{
        background: {PALETTE['background']};
        border: solid {PALETTE['blue']};
        color: {PALETTE['ink']};
        margin-bottom: 1;
    }}

    Input:focus {{
        border: solid {PALETTE['yellow']};
    }}

    #update-buttons {{
        margin-top: 2;
        height: 3;
        align: center middle;
    }}

    Button {{
        margin: 0 1;
    }}

    #btn-save {{ background: {PALETTE['teal']}; color: {PALETTE['background']}; }}
    #btn-cancel {{ background: {PALETTE['pink']}; color: {PALETTE['background']}; }}
    """

    def compose(self) -> ComposeResult:
        with Container(id="update-container"):
            yield Label(f"🌸 [bold yellow]Update Log #{self.log_data['id']}[/]", id="modal-title")
            
            yield Label("Status (TODO, WIP, DONE, FAILED):", classes="field-label")
            yield Input(value=self.log_data['status'], id="update-status")
            
            yield Label("Progress (0-100):", classes="field-label")
            yield Input(value=str(self.log_data['progress']), id="update-progress")
            
            yield Label("Tags:", classes="field-label")
            yield Input(value=self.log_data.get('tags', '') or "", placeholder="e.g. feature, fix", id="update-tags")
            
            with Horizontal(id="update-buttons"):
                yield Button("Save 🌸", id="btn-save")
                yield Button("Cancel", id="btn-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-save":
            try:
                progress = int(self.query_one("#update-progress", Input).value.strip())
            except ValueError:
                self.app.notify("Progress must be a number! 🌸", severity="error")
                return
                
            data = {
                "id": self.log_data['id'],
                "status": self.query_one("#update-status", Input).value.strip().upper(),
                "progress": progress,
                "tags": self.query_one("#update-tags", Input).value.strip()
            }
            self.dismiss(data)
        else:
            self.dismiss(None)

if __name__ == "__main__":
    app = FlowlogApp()
    app.run()
