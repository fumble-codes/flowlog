import typer
from datetime import datetime, timedelta
from rich.console import Console
from rich.table import Table
from ai_utils import get_gemini_model_for, smart_parse_task, infer_tags_local, ai_generate_content
from db import get_last_log_date, add_log, get_db_connection, delete_log

console = Console()

def estimate_progress(description: str) -> int:
    if not description:
        return 10
    text = description.lower()
    high = ["fixed", "completed", "shipped", "deployed", "launched", "finished", "implemented", "delivered", "resolved"]
    medium = ["worked", "built", "developed", "coding", "wrote", "designed", "created", "refactored", "testing", "debugging", "edited"]
    low = ["research", "planning", "read", "explored", "setup", "learned", "meeting", "outreach", "dm", "college", "gym", "chill", "chilling", "rest"]
    amp_pos = ["major", "big", "significant", "critical", "important", "high-end", "deep", "intensive"]
    amp_neg = ["small", "minor", "brief", "few", "little", "partial", "mostly"]
    score = 0
    for w in high:
        if w in text:
            score += 40
    for w in medium:
        if w in text:
            score += 25
    for w in low:
        if w in text:
            score += 10
    mult = 1.0
    for w in amp_pos:
        if w in text:
            mult *= 1.3
    for w in amp_neg:
        if w in text:
            mult *= 0.7
    dur = 0
    import re
    m = re.search(r"(\d+)\s*(h|hour|hours)", text)
    if m:
        hrs = int(m.group(1))
        dur += min(hrs, 8) * 4
    if "all day" in text:
        dur += 30
    if "most of the day" in text:
        dur += 20
    if "many" in text:
        dur += 10
    if "few" in text:
        dur -= 5
    score = int((score * mult) + dur)
    score = max(5, min(95, score))
    if "finished" in text or "completed" in text or "shipped" in text or "deployed" in text:
        score = max(score, 85)
    return score

DOMAIN_TITLES = {
    "gym": "Gym workout",
    "college": "College",
    "coding": "Coding work",
    "design": "Design work",
    "bugfix": "Bug fixing",
    "deploy": "Deployment",
    "outreach": "Outreach",
    "meeting": "Meeting",
    "research": "Research",
    "chill": "Chill / Rest",
    "qsi": "QSI site work",
    "groovsta": "Groovsta client work",
    "webmatic": "Webmatic client work",
    "development": "Development",
    "deployment": "Deployment",
    "production": "Production update",
    "networking": "Networking",
}

CANONICAL_TAGS = {
    "fitness": "gym",
    "workout": "gym",
    "health": "gym",
    "code": "coding",
    "coding": "coding",
    "develop": "coding",
    "development": "coding",
    "programming": "coding",
    "deploy": "deploy",
    "deployment": "deploy",
    "ship": "deploy",
    "release": "deploy",
    "launched": "deploy",
    "bugfix": "bugfix",
    "debug": "bugfix",
    "fix": "bugfix",
    "issue": "bugfix",
    "error": "bugfix",
    "resolved": "bugfix",
    "outreach": "outreach",
    "dm": "outreach",
    "cold": "outreach",
    "cold-call": "outreach",
    "cold call": "outreach",
    "meeting": "meeting",
    "call": "meeting",
    "sync": "meeting",
    "standup": "meeting",
    "research": "research",
    "read": "research",
    "learned": "research",
    "planning": "research",
    "plan": "research",
    "chill": "chill",
    "rest": "chill",
    "break": "chill",
    "relax": "chill",
    "qsi": "qsi",
    "groovsta": "groovsta",
    "webmatic": "webmatic",
    "flowlog": "flowlog",
    "personal": "chill"
}

def extract_metrics(desc: str):
    import re
    text = (desc or "").lower()
    metrics = {"dms": None, "calls": None, "meta_reachouts": None}
    m = re.search(r"\b(dm|dms|direct messages?)\b\s*(?:=|:)?\s*(\d+)", text)
    if m:
        metrics["dms"] = int(m.group(2))
    m = re.search(r"cold\s+call(?:ed|s)?\s*(\d+)\s*-\s*(\d+)", text)
    if m:
        metrics["calls"] = f"{m.group(1)}-{m.group(2)}"
    else:
        m = re.search(r"cold\s+call(?:ed|s)?\s*(?:=|:)?\s*(\d+)", text)
        if m:
            metrics["calls"] = int(m.group(1))
    m1 = re.search(r"reachout.*meta\s+ad.*(?:=|:)\s*(\d+)", text)
    m2 = re.search(r"meta\s+ad.*reachout.*(?:=|:)\s*(\d+)", text)
    if m1 or m2:
        metrics["meta_reachouts"] = int((m1 or m2).group(1))
    return metrics

def synthesize_title(domain: str, desc: str, fallback: str) -> str:
    return fallback or "Untitled"

def _month_to_num(mon: str) -> int:
    m = mon.strip().lower()
    names = ["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"]
    for i,n in enumerate(names,1):
        if m.startswith(n):
            return i
    return 1

def _parse_paragraph_locally(start_date: str, end_date: str, paragraph: str):
    import re
    sd = datetime.strptime(start_date, "%Y-%m-%d").date()
    ed = datetime.strptime(end_date, "%Y-%m-%d").date()
    text = paragraph
    pattern = re.compile(r"(\d{1,2})(?:\s*-\s*(\d{1,2}))?\s*(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)", re.IGNORECASE)
    matches = list(pattern.finditer(text))
    if not matches:
        return []
    segments = []
    for i, m in enumerate(matches):
        s = m.end()
        e = matches[i+1].start() if i+1 < len(matches) else len(text)
        segments.append((m.group(1), m.group(2), m.group(3), text[s:e].strip()))
    items = []
    for d1, d2, mon, seg in segments:
        day_start = int(d1)
        day_end = int(d2) if d2 else int(d1)
        month_num = _month_to_num(mon)
        year = sd.year if month_num == sd.month else ed.year
        for day in range(day_start, day_end+1):
            try:
                dt = datetime(year, month_num, day).date()
            except:
                continue
            if dt < sd or dt > ed:
                continue
            tags = infer_tags_local(seg)
            if not tags:
                tags = []
            prog = estimate_progress(seg)
            title = "Activity"
            dom = tags[0] if tags else None
            if dom:
                title = synthesize_title(dom, seg, title)
            items.append({
                "date": dt.isoformat(),
                "title": title,
                "description": seg,
                "progress": prog,
                "tags": tags
            })
    if not items:
        return []
    items = _split_by_domain(items)
    return items

def _split_by_domain(items: list):
    return items

def _consolidate_per_date_domain(items: list):
    return items

def _coalesce_domains(items: list):
    return items

def _dedup_entries(items: list):
    from itertools import groupby
    key_fn = lambda e: (e.get("date"), (e.get("tags") or [""])[0] or e.get("title") or "")
    items_sorted = sorted(items, key=key_fn)
    deduped = []
    for key, group in groupby(items_sorted, key=key_fn):
        group_list = list(group)
        if len(group_list) == 1:
            deduped.append(group_list[0])
            continue
        date, primary = key
        descs = [g.get("description","") for g in group_list]
        max_prog = max(int(g.get("progress",0)) for g in group_list)
        tags_union = []
        for g in group_list:
            for t in g.get("tags", []) or []:
                if t and t not in tags_union:
                    tags_union.append(t)
        title = group_list[0].get("title") or primary or "Activity"
        deduped.append({
            "date": date,
            "title": title,
            "description": " | ".join([d for d in descs if d]),
            "progress": max_prog,
            "tags": tags_union or [primary] if primary else []
        })
    return deduped
def _date_range_from_last(last_date_str: str):
    today = datetime.now().date()
    last_date = datetime.strptime(last_date_str, "%Y-%m-%d").date()
    diff = (today - last_date).days
    if diff <= 1:
        return None
    start = last_date + timedelta(days=1)
    return start, today, diff

def detect_gap():
    last = get_last_log_date()
    if not last:
        return None
    return _date_range_from_last(last)

def _build_prompt(start_date: str, end_date: str, paragraph: str):
    return f"""
You are processing activity logs for a CLI productivity tool.
User describes activities for a missing date range.
Split the paragraph into daily logs. When multiple distinct activities occur on the same date, create multiple entries for that date (one entry per distinct task/project).
Constraints:
- Only use dates within the given range
- Do not invent activities
- If a day has no information, skip it
- Return JSON array
- Each item must contain: date, title, description, progress (0-100), tags
- Estimate progress from description: use lower scores for light activity and higher scores for substantial work. Keep conservative estimates.
- Tags: Provide a list of free-form tags suggested by the content (no fixed taxonomy). Prefer concise tags like project names and activity types.
- Do not group multiple tasks into a single title. Prefer separate entries with clear titles.
- Respect any 'daily' schedules and explicit exceptions mentioned (e.g., no gym on specified days).
Date format: YYYY-MM-DD
Range: {start_date} → {end_date}
User text:
{paragraph}
"""

def send_text_to_llm(start_date: str, end_date: str, paragraph: str):
    prompt = _build_prompt(start_date, end_date, paragraph)
    try:
        import os
        os.environ["GEMINI_MODEL_CANDIDATES"] = "gemini-2.5-flash,gemini-3-flash,gemini-2.5-flash-lite"
        content = ai_generate_content(prompt)
        if not content:
            raise Exception("no_ai")
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        import json
        data = json.loads(content)
        normalized = []
        for item in data:
            d = item.get("date") or start_date
            t = item.get("title") or "Untitled"
            desc = item.get("description") or t
            prog = item.get("progress")
            try:
                prog = int(prog) if prog is not None else None
            except:
                prog = None
            if prog is None or prog == 0:
                prog = estimate_progress(desc)
            try:
                prog = int(prog)
            except:
                prog = 0
            tags = item.get("tags") or []
            if isinstance(tags, str):
                raw = tags.replace("&", ",").replace(" and ", ",")
                tags_list = [x.strip() for x in raw.split(",") if x.strip()]
            else:
                tags_list = [str(x).strip() for x in tags if str(x).strip()]
            try:
                from ai_utils import infer_tags_local
                local_tags = infer_tags_local(desc)
                for lt in local_tags:
                    if lt not in tags_list:
                        tags_list.append(lt)
            except:
                pass
            if not tags_list:
                try:
                    parsed = smart_parse_task(desc)
                    if parsed:
                        parsed_tags = parsed.get("tags", "")
                        if isinstance(parsed_tags, str):
                            raw = parsed_tags.replace("&", ",").replace(" and ", ",")
                            tags_list = [x.strip() for x in raw.split(",") if x.strip()]
                        elif isinstance(parsed_tags, list):
                            tags_list = [str(x).strip() for x in parsed_tags if str(x).strip()]
                except:
                    pass
            normalized.append({
                "date": d,
                "title": t,
                "description": desc,
                "progress": max(0, min(100, prog)),
                "tags": tags_list
            })
        normalized = _dedup_entries(normalized)
        return normalized
    except Exception:
        local_items = _parse_paragraph_locally(start_date, end_date, paragraph.strip())
        if local_items:
            return local_items
        tags_list = infer_tags_local(paragraph.strip())
        return [{
            "date": start_date,
            "title": "Gap summary",
            "description": paragraph.strip(),
            "progress": estimate_progress(paragraph.strip()),
            "tags": tags_list or ["summary"]
        }]

def preview_generated_logs(items: list):
    from ui import header, footer
    console.print(header("Gap Recovery Preview"))
    
    table = Table(box=box.SIMPLE, border_style=role_color("border"), expand=True)
    table.add_column("Date", style="cyan", width=12)
    table.add_column("Title", style="bold")
    table.add_column("Progress", width=20)
    table.add_column("Tags", style="dim")
    
    for it in items:
        from table_style import render_progress
        prog = it.get("progress", 0)
        tags = ", ".join(it.get("tags", []))
        table.add_row(it["date"], it["title"], render_progress(prog), tags)
    
    console.print(table)
    
    # Dedup indicator logic (simple check)
    original_count = len(items) # This is a placeholder; in a real scenario we'd track the pre-dedup count
    console.print(f"\n[dim italic]AI processed activities and generated {original_count} unique entries.[/]")
    
    console.print(footer("[y] Save • [n] Cancel • [edit] Rewrite"))
    choice = typer.prompt("Select action", default="y").strip().lower()
    return choice

def save_generated_logs(items: list):
    for it in items:
        tags_str = ",".join(it.get("tags", []))
        due = it.get("date")
        add_log(it.get("title","Untitled"), it.get("description",""), "DONE", it.get("progress",0), tags_str, due, log_date=due)

def _infer_range_from_paragraph(paragraph: str, year_hint: int = None):
    import re
    mons = {"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,"jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12}
    text = paragraph.lower()
    tokens = []
    for m in re.finditer(r"(\d{1,2})\s*(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)", text):
        day = int(m.group(1)); mon = mons[m.group(2)]
        tokens.append((day, mon))
    if not tokens:
        return None
    y = year_hint or datetime.now().year
    dates = []
    for d, m in tokens:
        try:
            dates.append(datetime(y, m, d).date())
        except:
            continue
    if not dates:
        return None
    return min(dates).isoformat(), max(dates).isoformat()

def rehydrate_gap_summaries():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, title, description, due_date, created_at FROM logs WHERE title = 'Gap summary'")
    rows = cur.fetchall()
    conn.close()
    if not rows:
        return 0
    rehydrated = 0
    for row in rows:
        # tuple indices: (id, title, description, status, progress, created_at, updated_at, tags, due_date) in get_log_by_id
        try:
            log_id = row[0]
            paragraph = row[2] or ""
            due_date = row[3]
            created_at = row[4]
        except Exception:
            # sqlite Row case
            log_id = row["id"]
            paragraph = row["description"] or ""
            due_date = row["due_date"]
            created_at = row["created_at"]
        year_hint = None
        try:
            if due_date and due_date != "None":
                year_hint = datetime.strptime(due_date[:10], "%Y-%m-%d").year
            elif created_at:
                year_hint = datetime.fromisoformat(created_at).year
        except:
            year_hint = datetime.now().year
        rng = _infer_range_from_paragraph(paragraph, year_hint=year_hint)
        if not rng:
            continue
        start, end = rng
        items = send_text_to_llm(start, end, paragraph)
        if not items:
            continue
        # remove the summary and add detailed ones
        delete_log(log_id)
        save_generated_logs(items)
        rehydrated += 1
    return rehydrated
def check_and_run_gap_recovery():
    gap = detect_gap()
    if not gap:
        return
    start, end, days = gap
    console.print(f"You haven't logged for {days} days.")
    consent = typer.prompt("Fill the gap? (y/n)", default="y").strip().lower()
    if consent != "y":
        return
    console.print(f"Describe what happened between:\n{start.isoformat()} → {end.isoformat()}")
    paragraph = typer.prompt("Write a short paragraph")
    items = send_text_to_llm(start.isoformat(), end.isoformat(), paragraph)
    while True:
        choice = preview_generated_logs(items)
        if choice == "y":
            save_generated_logs(items)
            break
        if choice == "n":
            break
        if choice == "edit":
            paragraph = typer.prompt("Rewrite the paragraph")
            items = send_text_to_llm(start.isoformat(), end.isoformat(), paragraph)
