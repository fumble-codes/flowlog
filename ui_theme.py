PALETTE = {
    "background": "#24273a",  # Catppuccin Macchiato Surface0 (Softer than black)
    "pink": "#f5bde6",        # Pink (Vibrant yet soft)
    "blue": "#8aadf4",        # Blue
    "yellow": "#eed49f",      # Yellow
    "peach": "#f5a97f",       # Peach (Orange counterpart)
    "mauve": "#c6a0f6",       # Mauve (Purple)
    "teal": "#8bd5ca",        # Teal
    "sky": "#91d7e3",         # Sky Blue
    "lavender": "#b7bdf8",    # Lavender
    "ink": "#cad3f5",         # Text color
}

ROLES = {
    "title": PALETTE["mauve"],
    "success": PALETTE["teal"],
    "warning": PALETTE["yellow"],
    "error": PALETTE["pink"],
    "info": PALETTE["sky"],
    "border": PALETTE["blue"],
}

def role_color(name: str) -> str:
    return ROLES.get(name, PALETTE["ink"])

