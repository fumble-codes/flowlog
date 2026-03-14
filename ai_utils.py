import os
import sys
import warnings
import logging

# Suppress all warnings for a premium CLI feel
os.environ["PYTHONWARNINGS"] = "ignore"
warnings.filterwarnings("ignore")
logging.getLogger('google').setLevel(logging.ERROR)
logging.getLogger('requests').setLevel(logging.ERROR)

from datetime import datetime
import json
from dotenv import load_dotenv
import requests

class AIApiError(Exception):
    """Custom exception for AI API failures."""
    pass

# Handle Google AI SDK imports

_GENAI_NEW = False
genai = None

try:
    import logging
    logging.getLogger('google').setLevel(logging.ERROR)
    # Try the new google-genai SDK
    from google import genai as genai_new
    if hasattr(genai_new, 'Client'):
        genai = genai_new
        _GENAI_NEW = True
except (ImportError, AttributeError):
    pass

if not _GENAI_NEW:
    try:
        # Fallback to the legacy google-generativeai SDK
        import google.generativeai as genai_legacy
        genai = genai_legacy
        import warnings
        warnings.filterwarnings("ignore", category=FutureWarning)
        warnings.filterwarnings("ignore", category=UserWarning)
    except ImportError:
        genai = None

# Load .env - support both dev and PyInstaller modes
if getattr(sys, 'frozen', False):
    # Running as exe - .env is bundled next to exe
    env_path = os.path.join(os.path.dirname(sys.executable), '.env')
else:
    env_path = '.env'
load_dotenv(env_path)

def _get_gemini_client():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or genai is None:
        return None
    if _GENAI_NEW:
        try:
            return genai.Client(api_key=api_key)
        except Exception:
            return None
    else:
        try:
            genai.configure(api_key=api_key)
            return True  # signal legacy configured
        except Exception:
            return None

def get_gemini_model_for(name: str):
    client = _get_gemini_client()
    if client is None:
        return None
    if _GENAI_NEW:
        return {"client": client, "model": name}
    else:
        try:
            return genai.GenerativeModel(name)
        except Exception:
            return None


def _call_kimi_api(prompt: str, model: str = "kimi-latest") -> str:
    """
    Call Kimi AI (Moonshot) API.
    """
    api_key = os.getenv("KIMI_API_KEY")
    if not api_key:
        return None
    
    url = "https://api.moonshot.cn/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    data = {
        "model": model,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7
    }
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=60)
        if response.status_code == 200:
            result = response.json()
            if "choices" in result and len(result["choices"]) > 0:
                return result["choices"][0]["message"]["content"]
        return None
    except Exception:
        return None


def _call_provider(prompt: str, provider: str) -> tuple[str, str]:
    """
    Call a specific AI provider and return (result, error).
    """
    if provider == "kimi":
        candidates_env = os.getenv("KIMI_MODEL_CANDIDATES")
        if candidates_env:
            candidates = [m.strip() for m in candidates_env.split(",") if m.strip()]
        else:
            candidates = ["kimi-latest", "kimi-flash-latest", "kimi-flash"]
        
        for model in candidates:
            result = _call_kimi_api(prompt, model)
            if result:
                return result, None
            continue
        return None, "All Kimi models failed"
    
    elif provider == "gemini":
        candidates_env = os.getenv("GEMINI_MODEL_CANDIDATES")
        if candidates_env:
            candidates = [m.strip() for m in candidates_env.split(",") if m.strip()]
        else:
            candidates = ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-3.1-flash-lite", "gemini-3-flash"]
        
        for name in candidates:
            model = get_gemini_model_for(name)
            if not model:
                continue
            try:
                if _GENAI_NEW:
                    resp = model["client"].models.generate_content(model=model["model"], contents=prompt)
                    text = getattr(resp, "text", None) or getattr(resp, "output_text", None)
                    if text:
                        return text.strip(), None
                else:
                    resp = model.generate_content(prompt)
                    text = getattr(resp, "text", None)
                    if text:
                        return text.strip(), None
            except Exception as e:
                continue
        
        return None, "All Gemini models failed"
    
    return None, f"Unknown provider: {provider}"

def ai_generate_content(prompt: str):
    order = os.getenv("AI_PROVIDER_ORDER", "gemini,kimi").split(",")
    last_error = None
    
    for provider in [p.strip().lower() for p in order]:
        result, error = _call_provider(prompt, provider)
        if result:
            return result
        if error:
            last_error = error
    
    if last_error:
        err_lower = last_error.lower()
        if "429" in err_lower or "quota" in err_lower or "exhausted" in err_lower:
            raise AIApiError("API Quota Exceeded. Please wait a minute and try again, or check your API billing limits.")
        elif "401" in err_lower or "auth" in err_lower or "api key" in err_lower:
            raise AIApiError("API Authentication Failed. Please check your API keys in the .env file.")
        elif "503" in err_lower or "unavailable" in err_lower:
            raise AIApiError("AI Service is temporarily unavailable. Please try again later.")
        else:
            raise AIApiError(f"AI Service Error: {last_error[:200]}... Please try again or check your connection.")
            
    return None
def get_real_time_context(last_log_time_str: str = None):
    """
    Generate context about the current time and last activity.
    """
    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S (%A)")
    
    context = f"Current Time: {now_str}\n"
    
    if last_log_time_str:
        try:
            last_log = datetime.fromisoformat(last_log_time_str)
            diff = now - last_log
            hours = diff.total_seconds() / 3600
            if hours < 1:
                context += f"Last activity was {int(diff.total_seconds() / 60)} minutes ago."
            elif hours < 24:
                context += f"Last activity was {int(hours)} hours ago."
            else:
                context += f"Last activity was {int(hours / 24)} days ago."
        except:
            pass
            
    return context

def study_user_patterns(logs_data: list):
    """
    Analyze all logs to understand user behavior, focus, and psychology.
    """
    # Compact logs for analysis to save tokens
    history = []
    for log in logs_data:
        history.append({
            "t": log["title"],
            "s": log["status"],
            "p": log["progress"],
            "d": log.get("log_date") or (log.get("created_at")[:10] if log.get("created_at") else ""),
            "tags": log["tags"]
        })

    prompt = f"""
    Study these project logs to build a deep psychological and behavioral profile of the user.
    
    Logs Data: {json.dumps(history)}

    Analyze the following categories using the activity date ('d'):
    1. Working Patterns: When are they most active? What's their sprint cycle?
    2. Focus Areas: What topics dominate their work? What do they prioritize?
    3. Behavioral Archetype: Are they a 'Closer', a 'Dreamer', a 'Consistent Grinder', or a 'Chaos Worker'? Explain why.
    4. Procrastination vs. Flow: When do they stall? What triggers their flow state?
    5. Psychological State: Based on the language in titles/descriptions and progress patterns, what is their general mindset?

    Return a comprehensive profile in JSON format with these keys:
    - summary (string)
    - archetypes (list of strings)
    - working_hours (string)
    - focus_breakdown (list of strings)
    - psychological_profile (string)
    - smart_tips (list of strings)

    Return ONLY the JSON object.
    """

    content = ai_generate_content(prompt)
    if not content:
        return None
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0].strip()
    elif "```" in content:
        content = content.split("```")[1].split("```")[0].strip()
    return content

def smart_parse_task(user_prompt: str, user_profile_json: str = None):
    """
    Uses Gemini to parse a natural language task description into structured fields.
    """
    from utils import get_logical_date
    today = get_logical_date()
    
    # Extract summary from JSON profile for context
    user_context = ""
    if user_profile_json:
        try:
            profile = json.loads(user_profile_json)
            user_context = f"User Profile Summary: {profile.get('summary', '')}"
        except:
            pass

    prompt = f"""
    Today is {today}.
    {user_context}
    
    Task: Parse the user prompt into a structured JSON object.
    
    Status Heuristics:
    - DONE: Use if the user explicitly mentions finishing, completing, shipping, or resolving the task (e.g., "just finished", "shipped the feature", "finally fixed x").
    - WIP: Use if the user mentions currently working on, building, or being in the middle of a task (e.g., "working on x", "coding the y module", "investigating z").
    - FAILED: Use if the user mentions giving up, failing, or a task being impossible/blocked permanently (e.g., "couldn't finish x", "gave up on y", "failed to z").
    - TODO: Default for new plans or future intentions (e.g., "I need to do x", "should start y tomorrow").

    Fields:
    - title (string, required)
    - description (string, optional)
    - status (one of: TODO, WIP, DONE, FAILED)
    - progress (integer 0-100; if DONE set to 100, if TODO set to 0 unless specified)
    - tags (comma-separated string)
    - due_date (string in YYYY-MM-DD format, or null)

    User prompt: "{user_prompt}"

    Return ONLY the JSON object.
    """

    
    try:
        os.environ["GEMINI_MODEL_CANDIDATES"] = "gemini-2.5-flash,gemini-3-flash,gemini-2.5-flash-lite,gemini-3.1-flash-lite"
        content = ai_generate_content(prompt)
        if not content:
            return None
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
            
        return json.loads(content)
    except AIApiError:
        raise
    except Exception as e:
        return None


def generate_ai_summary(logs_data: list, user_profile_json: str = None, time_context: str = None):
    """
    Generates a motivational summary and productivity analysis based on logs.
    """
    # Extract summary from JSON profile for context
    user_context = ""
    if user_profile_json:
        try:
            profile = json.loads(user_profile_json)
            user_context = f"Long-term User Memory: {profile.get('summary', '')}"
        except:
            pass

    formatted_logs = []
    for log in logs_data:
        formatted_logs.append({
            "title": log["title"],
            "status": log["status"],
            "progress": log["progress"],
            "tags": log["tags"],
            "activity_date": log.get("log_date") or (log.get("updated_at")[:10] if log.get("updated_at") else "")
        })

    prompt = f"""
    {time_context if time_context else ""}
    {user_context}
    
    Analyze these project logs and provide:
    1. A concise summary of recent progress.
    2. A motivational 'hype' message tailored to their psychology and the current time.
    3. Psychological insight: Are they procrastinating? Are they on a roll? 
    4. One 'Smart Tip' for tomorrow.

    Logs: {json.dumps(formatted_logs)}
    Note: 'activity_date' represents the actual day the work was performed.

    Format the output using Rich-compatible tags like [bold green], [italic], etc. 
    Keep it punchy and engaging for a CLI user.
    """

    os.environ["GEMINI_MODEL_CANDIDATES"] = "gemini-2.5-pro,gemini-3-flash,gemini-2.5-flash,gemini-3.1-flash-lite,gemini-2.5-flash-lite"
    content = ai_generate_content(prompt)
    if content:
        return content
    return "AI not available; using offline features."

DOMAIN_TITLES = {
    "gym": "Gym Workout",
    "college": "College",
    "coding": "Coding Work",
    "design": "Design Work",
    "bugfix": "Bug Fixes",
    "deploy": "Deployment",
    "outreach": "Outreach",
    "meeting": "Meeting",
    "research": "Research",
    "chill": "Chill / Rest",
    "qsi": "QSI Site Work",
    "groovsta": "Groovsta Client Work",
    "webmatic": "Webmatic Client Work",
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
    return fallback or DOMAIN_TITLES.get(domain, "Activity")

def infer_tags_local(description: str) -> list[str]:
    if not description:
        return []
    text = description.lower()
    tags = set()
    mapping = {
        "gym": ["gym", "workout", "training"],
        "college": ["college", "class", "lecture", "assignment"],
        "coding": ["code", "coding", "develop", "development", "programming"],
        "design": ["design", "ui", "ux", "hero", "layout"],
        "bugfix": ["bug", "fix", "debug", "issue", "error", "resolved"],
        "deploy": ["deploy", "deployed", "ship", "shipped", "release", "launched"],
        "outreach": ["outreach", "email", "dm", "message", "cold"],
        "meeting": ["meeting", "call", "sync", "standup"],
        "research": ["research", "read", "learned", "explored", "planning", "plan"],
        "chill": ["chill", "chilling", "rest", "break", "relax"],
        "qsi": ["qsi"],
        "groovsta": ["groovsta", "social"],
        "webmatic": ["webmatic"],
        "flowlog": ["flowlog"]
    }
    for tag, keywords in mapping.items():
        for k in keywords:
            if k in text:
                tags.add(tag)
                break
    return list(tags)[:6]
