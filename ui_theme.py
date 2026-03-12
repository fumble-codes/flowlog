PALETTE = {
    "ink": "#333333",
    "muted": "#666A86",
    "blue": "#95B8D1",
    "cream": "#E8DDB5",
    "pink": "#EDAFB8",
}

ROLES = {
    "title": PALETTE["blue"],
    "success": PALETTE["cream"],
    "warning": PALETTE["pink"],
    "error": "#FF6B6B",
    "info": PALETTE["muted"],
    "border": PALETTE["muted"],
}

def role_color(name: str) -> str:
    return ROLES.get(name, PALETTE["ink"])

