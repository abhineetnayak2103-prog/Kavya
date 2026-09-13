# Kavya — Discord Bot

A full-featured moderation/utility bot built with **discord.py**, using
**hybrid commands** (works as both `!prefix` and `/slash`) and SQLite for
persistent storage. Every reply goes through one shared embed helper so the
whole bot has a single, consistent professional look.

## Categories

🌐 General · 🛡️ Moderation · ⚡ Antinuke · 🚨 Antiraid · 🤖 AutoMod ·
🎫 Tickets · 👋 Welcome · 📜 Logging · 🎨 Embed · 💬 Social · 🛠️ Utility ·
🎭 Roles · 🔊 Join2Create · 📊 Tracking · 🎙️ Voice · 👑 Owner (slash-only)

Run `!help` (or `/help`) in Discord for the interactive dropdown menu.

## Project layout

```
kavya/
├── main.py              # bot entrypoint, cog loader, error handler
├── config.py             # branding, colors, category metadata
├── requirements.txt
├── .env.example           # copy to .env and add your token
├── utils/
│   ├── database.py        # aiosqlite schema + connection
│   ├── embeds.py           # shared embed builder (success/error/info/warn)
│   └── checks.py            # permission check helpers
└── cogs/
    ├── general.py          # help menu, ping, avatar, poll, afk, snipe…
    ├── moderation.py         # kick/ban/mute/warn/purge/lock…
    ├── antinuke.py            # live protection + config commands
    ├── antiraid.py             # mass-join detection + config
    ├── automod.py               # antispam / antilink / antiword
    ├── tickets.py                 # button-based ticket system
    ├── welcome.py                  # welcomer channel/message/image
    ├── logging_cog.py               # 13-category event logging
    ├── embed_builder.py              # /embed, save & resend embeds
    ├── social.py                      # hug/slap/8ball/coinflip
    ├── utility.py                      # prefix, perms, bot settings
    ├── roles.py                         # role CRUD + bulk apply
    ├── join2create.py                    # dynamic voice rooms
    ├── tracking.py                        # message leaderboards
    ├── voice.py                            # VC moderation + vcrole
    └── owner.py                             # /owner (slash-only) group
```

## Setup

1. **Create the bot application** at https://discord.com/developers/applications,
   grab the token, and enable these **Privileged Gateway Intents**:
   - Server Members Intent
   - Message Content Intent

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Add your token**
   ```bash
   cp .env.example .env
   # then edit .env and paste your token in
   ```

4. **Invite the bot** with the `applications.commands` + `bot` scopes and
   Administrator permission (or a tighter custom set — see the permission
   decorators in each cog if you want to lock it down further).

5. **Run it**
   ```bash
   python main.py
   ```

   On first run Kavya creates `data/kavya.db` automatically and syncs all
   slash commands globally (can take up to an hour to propagate everywhere;
   for instant testing, sync to a single guild in `setup_hook` instead).

## Notes on what's "live" vs. config-only

- **Antinuke** and **Antiraid** actually listen to audit-log events / member
  joins and take action (ban/kick/strip roles) — not just toggles.
- **AutoMod** actively scans messages for spam bursts, links, and filtered
  words and deletes/punishes in real time.
- **Tickets** uses persistent Discord buttons (`Open Ticket`, `Claim`,
  `Close`) that survive bot restarts.
- **Join2Create** and **VC role** react to real voice-state updates.

## Extending it

Every cog sets a `category = "..."` class attribute — that's all the help
menu needs to pick it up automatically. To add a new command, just add a
method to the relevant cog (or a new cog + register it in `main.py`'s
`INITIAL_COGS` list) and it will show up in `!help <category>` for free.
