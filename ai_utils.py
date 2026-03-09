from datetime import datetime
import json
import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

def get_gemini_model():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None
    genai.configure(api_key=api_key)
    return genai.GenerativeModel('gemini-flash-lite-latest')

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
    model = get_gemini_model()
    if not model: return None

    # Compact logs for analysis to save tokens
    history = []
    for log in logs_data:
        history.append({
            "t": log["title"],
            "s": log["status"],
            "p": log["progress"],
            "u": log["updated_at"],
            "tags": log["tags"]
        })

    prompt = f"""
    Study these project logs to build a deep psychological and behavioral profile of the user.
    
    Logs Data: {json.dumps(history)}

    Analyze the following categories:
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

    try:
        response = model.generate_content(prompt)
        content = response.text.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        return content # Return as string JSON for DB storage
    except Exception as e:
        print(f"Study Error: {e}")
        return None

def smart_parse_task(user_prompt: str, user_profile_json: str = None):
    """
    Uses Gemini to parse a natural language task description into structured fields.
    """
    model = get_gemini_model()
    if not model:
        return None

    today = datetime.now().strftime("%Y-%m-%d (%A)")
    
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
    Parse the following user task description into a JSON object with these fields:
    - title (string, required)
    - description (string, optional)
    - status (one of: TODO, WIP, DONE, FAILED)
    - progress (integer 0-100)
    - tags (comma-separated string)
    - due_date (string in YYYY-MM-DD format, or null)

    User prompt: "{user_prompt}"

    Return ONLY the JSON object.
    """
    
    try:
        response = model.generate_content(prompt)
        content = response.text.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
            
        return json.loads(content)
    except Exception as e:
        print(f"AI Error: {e}")
        return None

def generate_ai_summary(logs_data: list, user_profile_json: str = None, time_context: str = None):
    """
    Generates a motivational summary and productivity analysis based on logs.
    """
    model = get_gemini_model()
    if not model:
        return "Gemini API key not found. Please set GEMINI_API_KEY in your .env file."

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
            "last_updated": log["updated_at"]
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

    Format the output using Rich-compatible tags like [bold green], [italic], etc. 
    Keep it punchy and engaging for a CLI user.
    """

    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return f"AI Error: {e}"
