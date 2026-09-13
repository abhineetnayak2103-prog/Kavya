"""
Kavya — Central configuration.
Secrets are loaded from a .env file (never hard-code your token).
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ---- Core ----
BOT_NAME = "Kavya"
TOKEN = os.getenv("KAVYA_TOKEN")
DEFAULT_PREFIX = "!"
DB_PATH = os.path.join(os.path.dirname(__file__), "data", "kavya.db")

# ---- Branding (used by utils/embeds.py) ----
COLOR_PRIMARY = 0x5865F2     # Kavya blurple
COLOR_SUCCESS = 0x57F287
COLOR_ERROR = 0xED4245
COLOR_WARNING = 0xFEE75C
COLOR_INFO = 0x5865F2

FOOTER_TEXT = "Kavya"
FOOTER_ICON = None  # set to your bot's avatar URL / hosted icon if you have one

# ---- Category metadata (emoji + description), mirrors the help menu ----
CATEGORIES = {
    "General":         {"emoji": "🌐", "description": "Everyday utility & fun tools."},
    "Moderation":       {"emoji": "🛡️", "description": "Warnings, purges, locks & member actions."},
    "Antinuke":         {"emoji": "⚡", "description": "Protects the server from malicious admins."},
    "Antiraid":         {"emoji": "🚨", "description": "Protects against mass-join raids."},
    "AutoMod":          {"emoji": "🤖", "description": "Antispam, antilink & bad-word filters."},
    "Tickets":          {"emoji": "🎫", "description": "Support ticket system."},
    "Welcome":          {"emoji": "👋", "description": "Custom welcome messages & images."},
    "Logging":          {"emoji": "📜", "description": "Server event logging across categories."},
    "Embed":            {"emoji": "🎨", "description": "Build & send custom embeds."},
    "Social":           {"emoji": "💬", "description": "Social & fun member commands."},
    "Utility":          {"emoji": "🛠️", "description": "Admin utility & info tools."},
    "Roles":            {"emoji": "🎭", "description": "Role management & bulk actions."},
    "Join2Create":      {"emoji": "🔊", "description": "Dynamic voice channel creation."},
    "Tracking":         {"emoji": "📊", "description": "Message leaderboards & profile stats."},
    "Voice":            {"emoji": "🎙️", "description": "Voice channel moderation tools."},
    "Owner":            {"emoji": "👑", "description": "Owner-only bot & server control."},
}
