def validate_status(status):
    valid_statuses = ["TODO", "WIP", "DONE"]
    if status.upper() not in valid_statuses:
        raise ValueError(f"Invalid status: {status}. Use one of {valid_statuses}")

def validate_title(title):
    if not title.strip():
        raise ValueError("Title cannot be empty or just spaces.")
