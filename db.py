import sqlite3
from datetime import datetime
from pathlib import Path
import os

APP_NAME = "Flowlog"
APP_DIR = Path(os.environ.get("APPDATA", Path.home())) / APP_NAME
APP_DIR.mkdir(parents=True, exist_ok=True)

DB_NAME = str(APP_DIR / "flowlog.db")
# DB_NAME = "progress_tracker.db"

def init_db(): #this function creates the table in the database if it doesnt exist already
    conn = sqlite3.connect(DB_NAME) #uses conn as an object to make a connection to the database
    cursor = conn.cursor()# conn.cursor() is a sqlite3 func which lets the code to manipulate the data in the database think of it as a pen which is being used to write in the dabase
    cursor.execute(''' 
            CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'TODO',
            progress INTEGER DEFAULT 0,
            created_at TEXT,
            updated_at TEXT,
            tags TEXT,
            due_date TEXT
            
        )
    ''') #cursor.execute execute the following sql script which is basic you will understand just by reading the script 
    conn.commit() # saves the action to the database for real , this is so important
    conn.close()  # closes the table to prevent memory leak 
def get_status_counts():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT status, COUNT(*) FROM logs GROUP BY status")
    rows = cursor.fetchall()
    conn.close()

    counts = {"TODO": 0, "WIP": 0, "DONE": 0}
    for status, cnt in rows:
        if status in counts:
            counts[status] = cnt
    return counts

def get_due_on(date_str: str):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, title, description, status, progress, tags, due_date
        FROM logs
        WHERE due_date IS NOT NULL
          AND due_date != 'None'
          AND substr(due_date,1,10) = ?
        ORDER BY status != 'DONE', progress ASC, title ASC
    """, (date_str,))
    rows = cursor.fetchall()
    conn.close()
    return rows
def add_log(title, description, status="TODO", progress=0, tags="",due_date="None"):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    created_at = updated_at = datetime.now().isoformat()
    cursor.execute("""
        INSERT INTO logs (title, description, status, progress, created_at, updated_at, tags , due_date)
        VALUES (?, ?, ?, ?, ?, ?, ?,?)
    """, (title, description, status, progress, created_at, updated_at, tags,due_date))
    conn.commit()
    conn.close()



def get_all_logs(): #yeah this shit gets all the logs to view in the cli
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, description, status, progress, created_at , updated_at FROM logs ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_all_logs_with_tags():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, title, description, status, progress, created_at, updated_at, tags
        FROM logs
        ORDER BY created_at DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows

def update_log(log_id, title=None, description=None, status=None, progress=None): #this command takes the log id of the task which has to be updated with the other inputs with to be updated as well  
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM logs WHERE id = ?", (log_id,)) 
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False  # signal log not found

    updated_title = title if title else row[1] #updates the title only when user inputs the title otherwise it remains the same 
    updated_description = description if description else row[2] #same as above
    updated_status = status if status else row[3]#same as above
    updated_progress = progress if progress is not None else row[4]  # progress column index (assuming order)
    updated_at = datetime.now().isoformat() #saves the update date and time 
    

    cursor.execute('''
        UPDATE logs 
        SET title = ?, description = ?, status = ?,progress = ?, updated_at = ?
        WHERE id = ?
    ''', (updated_title, updated_description, updated_status,  updated_progress,updated_at, log_id))

    conn.commit()
    conn.close()
    return True
def delete_log(log_id): #this is way too basic so i am assuming you prolly know this shit 
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM logs WHERE id = ?", (log_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False
    cursor.execute("DELETE FROM logs WHERE id = ?", (log_id,))
    conn.commit()
    conn.close()
    return True


def sort_logs(status=None, date=None, tag=None, sort_by="created_at", order="desc"):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    query = "SELECT * FROM logs WHERE 1=1"
    params = []

    if status:
        query += " AND status = ?"
        params.append(status)
    if date:
        query += " AND DATE(created_at) = ?"
        params.append(date)
    if tag:
        if isinstance(tag, list):
            # Multiple tags → match if any tag exists in the tags column
            tag_conditions = []
            for t in tag:
                tag_conditions.append("tags LIKE ?")
                params.append(f"%{t}%")
            query += " AND (" + " OR ".join(tag_conditions) + ")"
    # Safe-guarding sort_by input (optional)
    if sort_by not in ["created_at", "progress", "title", "status"]:
        sort_by = "created_at"
    if order.lower() not in ["asc", "desc"]:
        order = "desc"

    query += f" ORDER BY {sort_by} {order.upper()}"

    cursor.execute(query, tuple(params))
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_log_by_id(log_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM logs WHERE id = ?", (log_id,))
    row = cursor.fetchone()
    conn.close()
    return row
def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn



from datetime import datetime

def carry_log_to_date(log_id, new_date):
    """Carries a task to a new date by duplicating it with updated timestamps."""
    existing_log = get_log_by_id(log_id)
    if not existing_log:
        return None  # not found

    # full unpack (9 fields now)
    _, title, description, status, progress, created_at, updated_at, tags, due_date = existing_log

    if status.strip().upper() == "DONE":
        return "DONE_TASK"

    new_timestamp = datetime.fromisoformat(new_date).isoformat()

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO logs (title, description, status, progress, created_at, updated_at, tags, due_date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (title, description, status, progress, new_timestamp, new_timestamp, tags, new_date))

    conn.commit()
    conn.close()
    return True

def add_tags_column():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("ALTER TABLE logs ADD COLUMN tags TEXT DEFAULT ''")
        print("✅ 'tags' column added successfully.")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            print("⚠️ 'tags' column already exists.")
        else:
            raise
    conn.commit()
    conn.close()
from typing import List 
def get_active_logs() -> List[sqlite3.Row]:
    """Fetch logs with status todo or wip"""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
            SELECT * FROM logs 
            WHERE status IN ('TODO', 'WIP')
            ORDER BY updated_at DESC
            """)
    rows = cursor.fetchall()
    conn.close()
    return rows
def update_tags(log_id, tags_list):
    """Update tags for a specific log ID."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    tags_str = ",".join(tags_list) if tags_list else ""
    cursor.execute("UPDATE logs SET tags = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (tags_str, log_id))
    conn.commit()
    conn.close()
def get_logs_by_date(date_str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM logs
        WHERE DATE(created_at) = ?
        ORDER BY created_at DESC
    """, (date_str,))
    rows = cursor.fetchall()
    conn.close()
    return rows
def get_logs_by_due_date(target_date: str):
    """Return logs whose due_date is equal to target_date"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, title, description, status, progress, tags, due_date
        FROM logs
        WHERE due_date = ?
        ORDER BY id
    """, (target_date,))
    logs = cursor.fetchall()
    conn.close()
    return logs

def get_all_logs_with_due():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, title, description, status, progress, tags, due_date
        FROM logs
        ORDER BY id ASC
    """)
    logs = cursor.fetchall()
    conn.close()
    return logs

from pathlib import Path

if not Path("flowlog.db").exists():
    init_db()  # assuming you already have an init_db() function