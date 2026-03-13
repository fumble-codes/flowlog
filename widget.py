import tkinter as tk
from tkinter import ttk
import sys
import os
import subprocess
from pathlib import Path
from datetime import datetime

# Local imports
from ui_theme import PALETTE
from db import get_status_counts, add_log, get_db_connection

class FlowlogWidget:
    def __init__(self, root):
        self.root = root
        self.root.title("Flowlog Widget")
        
        # Widget dimensions (slightly larger for dashboard)
        self.width = 280
        self.height = 340
        
        # Screen position (bottom right-ish by default)
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = screen_width - self.width - 40
        y = screen_height - self.height - 80
        
        self.root.geometry(f"{self.width}x{self.height}+{x}+{y}")
        
        # Gadget-like behavior
        self.root.overrideredirect(True) # Frameless
        self.root.attributes("-toolwindow", True) # Hide from taskbar
        self.root.configure(bg=PALETTE["background"])
        
        # Pin to background (Windows specific trick)
        self.root.lower()
        
        # Variables
        self.todo_count = tk.StringVar(value="0")
        self.wip_count = tk.StringVar(value="0")
        self.done_count = tk.StringVar(value="0")
        self.progress_percent = tk.DoubleVar(value=0.0)
        
        self.setup_ui()
        self.refresh_data()
        
        # Dragging logic
        self.root.bind("<Button-1>", self.start_drag)
        self.root.bind("<B1-Motion>", self.do_drag)
        
        # Auto-refresh every 10 seconds
        self.root.after(10000, self.auto_refresh)

    def setup_ui(self):
        # Header
        header_frame = tk.Frame(self.root, bg=PALETTE["background"])
        header_frame.pack(fill="x", pady=(10, 5))
        
        tk.Label(
            header_frame, 
            text="FLOWLOG DASHBOARD", 
            font=("Segoe UI", 10, "bold"),
            bg=PALETTE["background"],
            fg=PALETTE["mauve"]
        ).pack()
        
        # Progress Bar Section
        progress_frame = tk.Frame(self.root, bg=PALETTE["background"])
        progress_frame.pack(fill="x", padx=15, pady=5)
        
        tk.Label(
            progress_frame, 
            text="OVERALL PROGRESS", 
            font=("Segoe UI", 7, "bold"),
            bg=PALETTE["background"],
            fg=PALETTE["lavender"]
        ).pack(anchor="w")
        
        self.canvas_progress = tk.Canvas(
            progress_frame, 
            height=8, 
            bg=PALETTE["background"], 
            highlightthickness=0
        )
        self.canvas_progress.pack(fill="x", pady=2)
        
        # Stats Grid
        stats_frame = tk.Frame(self.root, bg=PALETTE["background"])
        stats_frame.pack(fill="x", padx=10, pady=10)
        
        self.create_stat(stats_frame, "TODO", self.todo_count, PALETTE["yellow"])
        self.create_stat(stats_frame, "WIP", self.wip_count, PALETTE["blue"])
        self.create_stat(stats_frame, "DONE", self.done_count, PALETTE["teal"])
        
        # Recent Activity
        activity_label = tk.Label(
            self.root, 
            text="RECENT ACTIVITY", 
            font=("Segoe UI", 7, "bold"),
            bg=PALETTE["background"],
            fg=PALETTE["lavender"]
        )
        activity_label.pack(anchor="w", padx=15)
        
        self.activity_frame = tk.Frame(self.root, bg=PALETTE["background"])
        self.activity_frame.pack(fill="both", expand=True, padx=15, pady=5)
        
        # Quick Input
        input_container = tk.Frame(self.root, bg=PALETTE["background"], pady=5)
        input_container.pack(fill="x", side="bottom")
        
        input_frame = tk.Frame(input_container, bg=PALETTE["background"])
        input_frame.pack(fill="x", padx=15)
        
        tk.Label(
            input_frame, 
            text=">", 
            bg=PALETTE["background"], 
            fg=PALETTE["sky"], 
            font=("Consolas", 10, "bold")
        ).pack(side="left")
        
        self.entry = tk.Entry(
            input_frame,
            bg=PALETTE["background"],
            fg=PALETTE["ink"],
            insertbackground=PALETTE["pink"],
            relief="flat",
            font=("Segoe UI", 9),
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=PALETTE["blue"],
            highlightcolor=PALETTE["pink"]
        )
        self.entry.pack(side="left", fill="x", expand=True, padx=5)
        self.entry.bind("<Return>", self.handle_command)
        self.entry.focus_set()

    def create_stat(self, parent, label, var, color):
        frame = tk.Frame(parent, bg=PALETTE["background"])
        frame.pack(side="left", expand=True)
        
        tk.Label(
            frame, 
            textvariable=var, 
            font=("Segoe UI", 16, "bold"),
            bg=PALETTE["background"],
            fg=color
        ).pack()
        
        tk.Label(
            frame, 
            text=label, 
            font=("Segoe UI", 7, "bold"),
            bg=PALETTE["background"],
            fg=PALETTE["lavender"]
        ).pack()

    def update_progress_bar(self, percent):
        self.canvas_progress.delete("all")
        width = self.canvas_progress.winfo_width()
        if width <= 1: width = 250 # Fallback
        
        # Background
        self.canvas_progress.create_rectangle(
            0, 0, width, 8, 
            fill=PALETTE["blue"], # Using blue as semi-transparent-ish background
            stipple="gray25" if sys.platform != "win32" else "", # Stipple doesn't always work on Win
            outline=""
        )
        # Bar
        fill_width = (percent / 100.0) * width
        self.canvas_progress.create_rectangle(
            0, 0, fill_width, 8, 
            fill=PALETTE["mauve"], 
            outline=""
        )

    def refresh_data(self):
        try:
            # Stats
            counts = get_status_counts()
            todo = counts.get("TODO", 0)
            wip = counts.get("WIP", 0)
            done = counts.get("DONE", 0)
            
            self.todo_count.set(str(todo))
            self.wip_count.set(str(wip))
            self.done_count.set(str(done))
            
            # Progress
            total = todo + wip + done
            percent = (done / total * 100.0) if total > 0 else 0.0
            self.progress_percent.set(percent)
            self.update_progress_bar(percent)
            
            # Activity
            for widget in self.activity_frame.winfo_children():
                widget.destroy()
                
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT title, status FROM logs ORDER BY id DESC LIMIT 3")
            recent = cursor.fetchall()
            conn.close()
            
            if not recent:
                tk.Label(
                    self.activity_frame, 
                    text="No activity yet... 🌸", 
                    font=("Segoe UI", 8, "italic"),
                    bg=PALETTE["background"],
                    fg=PALETTE["lavender"]
                ).pack(pady=10)
            else:
                for log in recent:
                    row = tk.Frame(self.activity_frame, bg=PALETTE["background"])
                    row.pack(fill="x", pady=2)
                    
                    status = log["status"]
                    icon = "✅" if status == "DONE" else "🚧" if status == "WIP" else "📌"
                    color = PALETTE["teal"] if status == "DONE" else PALETTE["blue"] if status == "WIP" else PALETTE["yellow"]
                    
                    tk.Label(
                        row, 
                        text=icon, 
                        bg=PALETTE["background"], 
                        fg=color,
                        font=("Segoe UI", 9)
                    ).pack(side="left")
                    
                    title = log["title"]
                    if len(title) > 25: title = title[:22] + "..."
                    
                    tk.Label(
                        row, 
                        text=title, 
                        bg=PALETTE["background"], 
                        fg=PALETTE["ink"],
                        font=("Segoe UI", 9)
                    ).pack(side="left", padx=5)
                    
        except Exception as e:
            print(f"Error refreshing widget data: {e}")

    def auto_refresh(self):
        self.refresh_data()
        self.root.after(10000, self.auto_refresh)

    def handle_command(self, event):
        cmd_text = self.entry.get().strip()
        self.entry.delete(0, tk.END)
        
        if not cmd_text:
            return
            
        parts = cmd_text.split(" ", 1)
        action = parts[0].lower()
        
        if action == "tui":
            if sys.platform == "win32":
                subprocess.Popen(["start", "python", "tui.py"], shell=True)
            else:
                subprocess.Popen(["x-terminal-emulator", "-e", "python3 tui.py"])
            return

        title = parts[1] if len(parts) > 1 else ""
        if not title and action in ["add", "wip", "done"]:
            return
            
        if action == "add":
            add_log(title, "", status="TODO")
        elif action == "wip":
            add_log(title, "", status="WIP")
        elif action == "done":
            add_log(title, "", status="DONE", progress=100)
        
        self.refresh_data()

    def start_drag(self, event):
        self.x = event.x
        self.y = event.y

    def do_drag(self, event):
        deltax = event.x - self.x
        deltay = event.y - self.y
        x = self.root.winfo_x() + deltax
        y = self.root.winfo_y() + deltay
        self.root.geometry(f"+{x}+{y}")

if __name__ == "__main__":
    root = tk.Tk()
    app = FlowlogWidget(root)
    # Ensure canvas width is correct after first draw
    root.update()
    app.update_progress_bar(app.progress_percent.get())
    root.mainloop()
