# FLOWLOG (built with Typer + Rich + SQLite)

## 🔥 What it does
A modern **command-line productivity tracker** to:
- Log and carry tasks across dates  
- Track status: **TODO / WIP / DONE**  
- Add descriptions, tags, and progress percentages  
- View urgent tasks with **days left until due**  
- Search and filter logs by date, status, or tags  
- Auto-organize with **carry-forward logic** (unfinished tasks can be carried to today)

---

## 📁 Folder Structure

cli-project-tracker/ <br>
│ <br>
├── main.py              # CLI entry point (Typer commands + Rich UI)
<br>
├── db.py                # All DB logic: connect, CRUD, queries
<br>
├── validators.py        # Validation for title, status, tags, etc <br>
├── project_meta.md      # Project overview / roadmap <br>
└── flowlog.exe          # (Optional) Built executable via PyInstaller <br>

---

## 💾 Database

- SQLite DB file is **not stored inside the project folder anymore**.  
- It is now saved under the **user’s home directory** (platform-safe).  
  - Example (Windows):  
    C:\Users\<username>\flowlog\progress_tracker.db  
  - Example (Linux/macOS):  
    /home/<username>/.flowlog/progress_tracker.db  

This keeps the database persistent even if you move/delete the project folder.

---

## ⚙️ Commands

### 1. `add`
Add a new log.  
    python main.py add "Task title" --desc "desc" --status TODO --tags design,client

### 2. `view`
Show all logs in a Rich table.  
    python main.py view

### 3. `update`
Update a log by ID.  
    python main.py update 1 --progress 80 --status WIP

### 4. `delete`
Delete a log by ID.  
    python main.py delete 1

### 5. `query`
Filter logs by status, date, or tags.  
    python main.py query --status DONE  
    python main.py query --date 2025-08-17  
    python main.py query --tags design  

### 6. `carry`
Carry a task to today’s date.  
    python main.py carry 15

### 7. `home`
Dashboard-style view:  
- Urgent tasks (nearest due dates)  
- Remaining days until deadline  

    python main.py home

---

## 🧠 How it works (in simple terms)

- **main.py** → Defines CLI commands & interactive shell. Handles Rich output.  
- **db.py** → Handles SQLite storage, queries, carry-forward logic.  
- **validators.py** → Checks inputs like valid status, non-empty title, etc.  

---

## ✅ Current Status

- ✅ Core commands added  
- ✅ Carry-forward feature implemented  
- ✅ Urgent tasks dashboard (`home`)  
- ✅ Database stored in **user home directory**  
- ✅ Rich tables with **days left until due**  
- 🚧 Export/import (Phase 3)  
- 🚧 AI features (summaries, reminders)  

---

## 🔁 Quick Start

1. Install requirements:  
       pip install -r requirements.txt

2. Run help:  
       python main.py --help

3. Explore commands like `add`, `view`, `carry`.

---

## 🧩 Tip
If you come back later and forget:
- Open **project_meta.md** (this file)  
- Run `python main.py --help`  
- Check **db.py** for queries  
- Run `python main.py home` for dashboard  
