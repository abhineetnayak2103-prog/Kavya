"""
utils/database.py — single aiosqlite connection + schema + small helper
functions. Every cog imports `db` (the Database instance attached to the
bot) rather than touching SQL directly wherever possible.
"""
from __future__ import annotations
import aiosqlite
import json
import time
from typing import Any, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS guild_settings (
    guild_id INTEGER PRIMARY KEY,
    prefix TEXT DEFAULT '!'
);

CREATE TABLE IF NOT EXISTS warnings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER,
    user_id INTEGER,
    moderator_id INTEGER,
    reason TEXT,
    created_at INTEGER
);

CREATE TABLE IF NOT EXISTS antinuke_settings (
    guild_id INTEGER PRIMARY KEY,
    enabled INTEGER DEFAULT 0,
    punishment TEXT DEFAULT 'ban',
    log_channel_id INTEGER,
    strict_mode INTEGER DEFAULT 0,
    lockdown INTEGER DEFAULT 0,
    panic_mode INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS antinuke_owners (
    guild_id INTEGER,
    user_id INTEGER,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS antinuke_whitelist (
    guild_id INTEGER,
    entity_id INTEGER,
    entity_type TEXT,  -- 'user' or 'role'
    PRIMARY KEY (guild_id, entity_id, entity_type)
);

CREATE TABLE IF NOT EXISTS antinuke_offenses (
    guild_id INTEGER,
    user_id INTEGER,
    count INTEGER DEFAULT 0,
    window_start INTEGER,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS antiraid_settings (
    guild_id INTEGER PRIMARY KEY,
    enabled INTEGER DEFAULT 0,
    action TEXT DEFAULT 'kick',
    threshold INTEGER DEFAULT 10,
    window_seconds INTEGER DEFAULT 10,
    lockdown INTEGER DEFAULT 0,
    age_limit_days INTEGER DEFAULT 0,
    verification_upgrade INTEGER DEFAULT 0,
    avatar_check INTEGER DEFAULT 0,
    delete_invites INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS automod_settings (
    guild_id INTEGER PRIMARY KEY,
    antispam_enabled INTEGER DEFAULT 0,
    antilink_enabled INTEGER DEFAULT 0,
    antiword_enabled INTEGER DEFAULT 0,
    punishment TEXT DEFAULT 'warn'
);

CREATE TABLE IF NOT EXISTS automod_whitelist (
    guild_id INTEGER,
    module TEXT,       -- 'antispam' | 'antilink' | 'antiword'
    entity_id INTEGER,
    entity_type TEXT,  -- 'user' | 'role'
    PRIMARY KEY (guild_id, module, entity_id, entity_type)
);

CREATE TABLE IF NOT EXISTS bad_words (
    guild_id INTEGER,
    word TEXT,
    PRIMARY KEY (guild_id, word)
);

CREATE TABLE IF NOT EXISTS welcomer_settings (
    guild_id INTEGER PRIMARY KEY,
    enabled INTEGER DEFAULT 0,
    channel_id INTEGER,
    message TEXT DEFAULT 'Welcome {user.mention} to **{guild.name}**! We are now {guild.member_count} members strong.',
    image_url TEXT,
    embed_json TEXT
);

CREATE TABLE IF NOT EXISTS logging_settings (
    guild_id INTEGER,
    category TEXT,
    channel_id INTEGER,
    PRIMARY KEY (guild_id, category)
);

CREATE TABLE IF NOT EXISTS tickets_settings (
    guild_id INTEGER PRIMARY KEY,
    category_id INTEGER,
    log_channel_id INTEGER,
    support_role_id INTEGER,
    panel_channel_id INTEGER,
    panel_message_id INTEGER,
    ticket_counter INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS active_tickets (
    channel_id INTEGER PRIMARY KEY,
    guild_id INTEGER,
    user_id INTEGER,
    opened_at INTEGER,
    claimed_by INTEGER
);

CREATE TABLE IF NOT EXISTS afk_status (
    guild_id INTEGER,
    user_id INTEGER,
    reason TEXT,
    since INTEGER,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS message_stats (
    guild_id INTEGER,
    user_id INTEGER,
    day TEXT,
    count INTEGER DEFAULT 0,
    PRIMARY KEY (guild_id, user_id, day)
);

CREATE TABLE IF NOT EXISTS saved_embeds (
    guild_id INTEGER,
    name TEXT,
    embed_json TEXT,
    PRIMARY KEY (guild_id, name)
);

CREATE TABLE IF NOT EXISTS vcrole_settings (
    guild_id INTEGER PRIMARY KEY,
    role_id INTEGER
);

CREATE TABLE IF NOT EXISTS join2create_settings (
    guild_id INTEGER PRIMARY KEY,
    trigger_channel_id INTEGER,
    category_id INTEGER,
    name_template TEXT DEFAULT "{user.name}'s Room"
);

CREATE TABLE IF NOT EXISTS join2create_channels (
    channel_id INTEGER PRIMARY KEY,
    guild_id INTEGER,
    owner_id INTEGER
);

CREATE TABLE IF NOT EXISTS bot_admins (
    guild_id INTEGER,
    user_id INTEGER,
    role TEXT,  -- 'admin' or 'mod'
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS owner_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER,
    actor_id INTEGER,
    action TEXT,
    detail TEXT,
    created_at INTEGER
);
"""


class Database:
    def __init__(self, path: str):
        self.path = path
        self.conn: Optional[aiosqlite.Connection] = None

    async def connect(self):
        self.conn = await aiosqlite.connect(self.path)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.executescript(SCHEMA)
        await self.conn.commit()

    async def close(self):
        if self.conn:
            await self.conn.close()

    # ---------- generic helpers ----------
    async def execute(self, query: str, params: tuple = ()):
        await self.conn.execute(query, params)
        await self.conn.commit()

    async def fetchone(self, query: str, params: tuple = ()):
        cur = await self.conn.execute(query, params)
        row = await cur.fetchone()
        await cur.close()
        return row

    async def fetchall(self, query: str, params: tuple = ()):
        cur = await self.conn.execute(query, params)
        rows = await cur.fetchall()
        await cur.close()
        return rows

    # ---------- prefix ----------
    async def get_prefix(self, guild_id: int, default: str) -> str:
        row = await self.fetchone(
            "SELECT prefix FROM guild_settings WHERE guild_id = ?", (guild_id,)
        )
        return row["prefix"] if row and row["prefix"] else default

    async def set_prefix(self, guild_id: int, prefix: str):
        await self.execute(
            "INSERT INTO guild_settings (guild_id, prefix) VALUES (?, ?) "
            "ON CONFLICT(guild_id) DO UPDATE SET prefix = excluded.prefix",
            (guild_id, prefix),
        )

    # ---------- audit log (owner actions) ----------
    async def log_owner_action(self, guild_id: int, actor_id: int, action: str, detail: str = ""):
        await self.execute(
            "INSERT INTO owner_audit (guild_id, actor_id, action, detail, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (guild_id, actor_id, action, detail, int(time.time())),
        )
