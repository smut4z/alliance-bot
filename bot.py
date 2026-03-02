import os
import re
import cv2
import pytesseract
import tempfile
import discord
import json
import time
import asyncio
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone

MSK = timezone(timedelta(hours=3))
CAPT_CMDS_RE = re.compile(r"(\d{1,2})\s*([+-])")

ALLY_GUILD_ID = 1463849134380552374

GUILD_CONFIG = {
    652465386603675649: {
        "LOG_CHANNEL_ID": 975808442172325898,

        
        "ACTIVITY_VOICE_SOURCE": "both",

        
        "SELF_REQUIRED_LEFT": None,          
        "ALLY_REQUIRED_LEFT": "Alliance",    
    },

    1282692203839225977: {
        "LOG_CHANNEL_ID": 1282692205257162839,
        "ACTIVITY_VOICE_SOURCE": "both",
        "SELF_REQUIRED_LEFT": None,
        "ALLY_REQUIRED_LEFT": "Alliance",
    },
    1463849134380552374: {
        "LOG_CHANNEL_ID": 1463849134816628840,
    }
}

DATA_DIR = "/data"
os.makedirs(DATA_DIR, exist_ok=True)

BIRTHDAYS_FILE = Path(DATA_DIR) / "birthdays.json"
VOICE_STATS_FILE = Path(DATA_DIR) / "voice_stats.json"
ROLLBACK_FILE = Path(DATA_DIR) / "rollback_stats.json"
IC_FILE = Path(DATA_DIR) / "ic_vacations.json"

# ================== ENV ==================

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")

BIRTHDAY_PANEL_CHANNEL_ID = int(os.getenv("BIRTHDAY_PANEL_CHANNEL_ID"))
BIRTHDAY_STAFF_CHANNEL_ID = int(os.getenv("BIRTHDAY_STAFF_CHANNEL_ID"))
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID"))
IC_REQUEST_CHANNEL_ID = int(os.getenv("IC_REQUEST_CHANNEL_ID"))
ACTIVITY_CHANNEL_ID = int(os.getenv("ACTIVITY_CHANNEL_ID"))
ACTIVITY_REPORT_CHANNEL_ID = int(os.getenv("ACTIVITY_REPORT_CHANNEL_ID"))
ANALYZE_CHANNEL_ID = int(os.getenv("ANALYZE_CHANNEL_ID"))
DISCIPLINE_ROLE_ID = int(os.getenv("DISCIPLINE_ROLE_ID"))
VOICE_CHANNEL_ID = int(os.getenv("VOICE_CHANNEL_ID"))
FAMILY_REQUEST_CHANNEL_ID = int(os.getenv("FAMILY_REQUEST_CHANNEL_ID"))
FAMILY_REQUESTS_CHANNEL_ID = int(os.getenv("FAMILY_REQUESTS_CHANNEL_ID"))
CURATOR_ROLE_ID = int(os.getenv("CURATOR_ROLE_ID"))
TICKET_CATEGORY_ID = int(os.getenv("TICKET_CATEGORY_ID"))
TICKET_ARCHIVE_CATEGORY_ID = int(os.getenv("TICKET_ARCHIVE_CATEGORY_ID"))
FAMILY_WAR_PANEL_CHANNEL = int(os.getenv("FAMILY_WAR_PANEL_CHANNEL"))
FAMILY_WAR_CHANNEL = int(os.getenv("FAMILY_WAR_CHANNEL"))
FAMILY_SPISOK_CHANNEL = int(os.getenv("FAMILY_SPISOK_CHANNEL"))
ROLLBACK_REQUEST_CHANNEL_ID = int(os.getenv("ROLLBACK_REQUEST_CHANNEL_ID"))
REPRIMAND_ROLE_ID = int(os.getenv("REPRIMAND_ROLE_ID"))
DISCIPLINE_CHANNEL_ID = int(os.getenv("DISCIPLINE_CHANNEL_ID"))
MEETING_VOICE_ID = int(os.getenv("MEETING_VOICE_ID"))
MEETING_PANEL_CHANNEL = int(os.getenv("MEETING_PANEL_CHANNEL"))
FAMILY_ROLE_ID = [
    int(x)
    for x in os.getenv("FAMILY_ROLE_ID", "").split(",")
    if x.strip().isdigit()
]
TIER_ROLES = {
    "tier1": 1425248070286839909,
    "tier2": 1425249207702392924,
    "tier3": 1425249369564909679,
    "owner": 1439739490234269717,
}
PLAYER_TICKET_CATEGORY_IDS = [
    int(x)
    for x in os.getenv("PLAYER_TICKET_CATEGORY_IDS", "").split(",")
    if x.strip().isdigit()
]
HIGH_STAFF_ROLE_IDS = [
    int(x.strip())
    for x in os.getenv("HIGH_STAFF_ROLE_IDS", "").split(",")
    if x.strip().isdigit()
]

PENALTY_ROLE_IDS = [
    int(x.strip())
    for x in os.getenv("PENALTY_ROLE_IDS", "").split(",")
    if x.strip().isdigit()
]
TICKET_CLOSE_ROLE_IDS = [
    int(x.strip())
    for x in os.getenv("TICKET_CLOSE_ROLE_IDS", "").split(",")
    if x.strip().isdigit()
]
OWNER_ROLE_IDS = [
    int(x.strip())
    for x in os.getenv("OWNER_ROLE_IDS", "").split(",")
    if x.strip().isdigit()
]
PUNISH_CHANNEL_ID = int(os.getenv("PUNISH_CHANNEL_ID"))
APPEAL_CHANNEL_ID = int(os.getenv("APPEAL_CHANNEL_ID"))
VOICE_TOP_CHANNEL_ID = int(os.getenv("VOICE_TOP_CHANNEL_ID"))
print("STAFF_ROLE_IDS:", HIGH_STAFF_ROLE_IDS)

VOICE_STATS = {}
ROLLBACK_REQUESTS = {}

MEETING_ABSENCE_DATA = {
    "approved": {},
    "manual_present": set(),
    "report_message_id": None
}

ticket_counter = 0

ACTIVITY_REPORTS: dict[int, dict] = {}


BIRTHDAYS = {
    # "1234567890": "28.01"
}

BIRTHDAY_DATE_RE = re.compile(r"^\s*(\d{2})\.(\d{2})\s*$")

CAPT_UPDATE_TASKS: dict[int, asyncio.Task] = {}
CAPT_UPDATE_LOCKS: dict[int, asyncio.Lock] = {}

def _capt_lock(capt_id: int) -> asyncio.Lock:
    lock = CAPT_UPDATE_LOCKS.get(capt_id)
    if not lock:
        lock = asyncio.Lock()
        CAPT_UPDATE_LOCKS[capt_id] = lock
    return lock

async def request_capt_list_update(guild: discord.Guild, capt_id: int, delay: float = 0.8):
    t = CAPT_UPDATE_TASKS.get(capt_id)
    if t and not t.done():
        return

    async def _job():
        await asyncio.sleep(delay)
        async with _capt_lock(capt_id):
            await request_capt_list_update(guild, capt_id)

    CAPT_UPDATE_TASKS[capt_id] = asyncio.create_task(_job())

LIST_KEY_MAP = {
    "inv": "both",
    "nv": "not_voice",
    "ic": "ic",
}

FIX_BY_TEXT_RE = re.compile(
    r"^\s*испр\s+(.+?)\s*(?:->|=>|=|\|)\s*(.+?)\s*$",
    re.IGNORECASE
)
FIX_BY_INDEX_RE = re.compile(
    r"^\s*испр\s+(inv|nv|ic)\s+(\d{1,3})\s+(.+?)\s*$",
    re.IGNORECASE
)
DELETE_BY_TEXT_RE = re.compile(
    r"^\s*удал\s+(.+?)\s*$",
    re.IGNORECASE
)

DELETE_BY_INDEX_RE = re.compile(
    r"^\s*удал\s+(inv|nv|ic)\s+(\d{1,3})\s*$",
    re.IGNORECASE
)

def _norm_key(s: str) -> str:
    return normalize_character_name(clean_player_name(s))

def is_family_member(member: discord.Member, family_roles: list[discord.Role], reprimand_role: discord.Role | None) -> bool:
    if member.bot:
        return False

    roles = set(member.roles)

    if reprimand_role and reprimand_role in roles:
        return True

    for r in family_roles:
        if r in roles:
            return True

    return False

def ticket_name_from_user(member: discord.Member) -> str:
    name = member.display_name.lower()

    if "|" in name:
        name = name.split("|", 1)[1]

    name = name.replace("_", "-")

    name = re.sub(r"[^a-z0-9а-я-]", "", name)

    return f"заявка-{name}"

def load_json(file_path, default):
    if not os.path.exists(file_path):
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(default, f, ensure_ascii=False, indent=4)
        return default

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = f.read().strip()
            if not data:
                return default
            return json.loads(data)
    except json.JSONDecodeError:
        return default


def save_json(file_path, data):
    def default_serializer(obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return str(obj)

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4, default=default_serializer)

def get_user_tier(member: discord.Member):
    for tier, role_id in TIER_ROLES.items():
        if any(r.id == role_id for r in member.roles):
            return tier
    return None

def load_voice_stats():
    if os.path.exists(VOICE_STATS_FILE):
        try:
            with open(VOICE_STATS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            daily = {int(k): v for k, v in data.get("daily_voice_time", {}).items()}
            sessions = data.get("voice_sessions", {}) or {}
            last_reset = data.get("last_reset_date")

            return daily, sessions, last_reset

        except (json.JSONDecodeError, ValueError, TypeError):
            return {}, {}, None

    return {}, {}, None


def save_voice_stats(daily_voice_time, voice_sessions, last_reset_date=None):
    data = {
        "daily_voice_time": {str(k): v for k, v in daily_voice_time.items()},
        "voice_sessions": voice_sessions,
        "last_reset_date": last_reset_date
    }
    with open(VOICE_STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_ic():
    if not IC_FILE.exists() or IC_FILE.stat().st_size == 0:
        return {}

    try:
        with open(IC_FILE, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except json.JSONDecodeError:
        return {}

def save_ic(data):
    with open(IC_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def cleanup_ic():
    now = datetime.now(timezone.utc)
    to_delete = []

    for uid, data in ic_vacations.items():
        try:
            until = datetime.fromisoformat(data["until"])
            if until <= now:
                to_delete.append(uid)
        except:
            to_delete.append(uid)

    for uid in to_delete:
        del ic_vacations[uid]

    if to_delete:
        save_ic(ic_vacations)

def get_meeting_attendance(guild: discord.Guild):
    channel = guild.get_channel(MEETING_VOICE_ID)
    if not channel:
        return set(), set()

    present = set(member for member in channel.members if not member.bot)

    manual_ids = MEETING_ABSENCE_DATA.get("manual_present", set())
    for uid in manual_ids:
        member = guild.get_member(uid)
        if member:
            present.add(member)

    family_roles = [guild.get_role(rid) for rid in FAMILY_ROLE_ID]
    family_roles = [r for r in family_roles if r]
    reprimand_role = guild.get_role(REPRIMAND_ROLE_ID)

    if not family_roles and not reprimand_role:
        return present, set()

    family_members = {
        m for m in guild.members
        if is_family_member(m, family_roles, reprimand_role)
    }

    approved_ids = set(MEETING_ABSENCE_DATA.get("approved", {}).keys())
    absent = {m for m in family_members if m not in present and m.id not in approved_ids}

    return present, absent





EMBED_FIELD_LIMIT = 1024

def chunk_lines(lines: list[str], limit: int = EMBED_FIELD_LIMIT) -> list[str]:
    """Склеивает строки в чанки так, чтобы каждый chunk <= limit."""
    chunks = []
    buf = ""

    for line in lines:
        candidate = (buf + "\n" + line) if buf else line
        if len(candidate) > limit:
            if buf:
                chunks.append(buf)
                buf = line
            else:
                chunks.append(line[:limit-3] + "…")
                buf = ""
        else:
            buf = candidate

    if buf:
        chunks.append(buf)

    return chunks


def add_list_field(embed: discord.Embed, title: str, lines: list[str]):
    if not lines:
        embed.add_field(name=title, value="—", inline=False)
        return

    chunks = chunk_lines(lines, EMBED_FIELD_LIMIT)

    for i, chunk in enumerate(chunks):
        name = title if i == 0 else f"{title} (продолжение {i+1})"
        embed.add_field(name=name, value=chunk, inline=False)

def reset_meeting_data():
    MEETING_ABSENCE_DATA["approved"] = {}
    MEETING_ABSENCE_DATA["manual_present"] = set()
    MEETING_ABSENCE_DATA["report_message_id"] = None

def parse_capt_cmds(text: str) -> list[tuple[int, str]]:
    cmds = []
    for num, sign in CAPT_CMDS_RE.findall(text):
        idx = int(num)
        if 1 <= idx <= 99:
            cmds.append((idx, sign))
    return cmds

def parse_capt_footer(embed: discord.Embed) -> tuple[int | None, list[int], list[int]]:
    if not embed or not embed.footer or not embed.footer.text:
        return None, [], []

    text = embed.footer.text
    parts = {}

    for chunk in text.split(";"):
        if ":" not in chunk:
            continue
        k, v = chunk.split(":", 1)
        parts[k.strip()] = v.strip()

    capt_id = int(parts["capt_id"]) if parts.get("capt_id", "").isdigit() else None

    def parse_ids(s: str) -> list[int]:
        if not s:
            return []
        out = []
        for x in s.split(","):
            x = x.strip()
            if x.isdigit():
                out.append(int(x))
        return out

    return capt_id, parse_ids(parts.get("main", "")), parse_ids(parts.get("reserve", ""))

def build_meeting_embed(guild: discord.Guild):
    present_in_voice, absent_set = get_meeting_attendance(guild)

    manual_ids = set(MEETING_ABSENCE_DATA.get("manual_present", set()))
    manual_members = [guild.get_member(uid) for uid in manual_ids if guild.get_member(uid)]

    present = list({m.id: m for m in list(present_in_voice) + manual_members}.values())

    approved = MEETING_ABSENCE_DATA.get("approved", {})
    approved_ids = {
        int(uid) for uid in approved.keys()
        if str(uid).isdigit()
    }
    absent = [m for m in absent_set if m.id not in approved_ids]

    embed = discord.Embed(title="📊 Отчёт собрания", color=discord.Color.blue())

    def chunk_list_safe(lst, n=20):
        for i in range(0, len(lst), n):
            chunk = lst[i:i+n]
            text = "\n".join(chunk) or "—"
            if len(text) > 1024:
                text = text[:1020] + "…"
            yield text

    present_list = [m.mention for m in present]
    for i, chunk in enumerate(chunk_list_safe(present_list)):
        embed.add_field(
            name=f"✅ Присутствовали ({len(present_list)})" if i == 0 else "⠀",
            value=chunk,
            inline=False
        )

    absent_list = [m.mention for m in absent]
    for i, chunk in enumerate(chunk_list_safe(absent_list)):
        embed.add_field(
            name=f"❌ Отсутствовали ({len(absent_list)})" if i == 0 else "⠀",
            value=chunk,
            inline=False
        )

    approved = MEETING_ABSENCE_DATA.get("approved", {})
    print("APPROVED RAW:", MEETING_ABSENCE_DATA.get("approved"))
    approved_list = []
    for uid_raw, reason in approved.items():
        try:
            uid = int(uid_raw)
        except (TypeError, ValueError):
            continue

        approved_list.append(f"<@{uid}> — {reason}")
    for i, chunk in enumerate(chunk_list_safe(approved_list)):
        embed.add_field(
            name=f"🚫 Отсутствовали с причиной ({len(approved_list)})" if i == 0 else "⠀",
            value=chunk,
            inline=False
        )

    return embed









#def has_discipline_role(member: discord.Member) -> bool:
 #   return any(role.id == DISCIPLINE_ROLE_ID for role in member.roles)

def has_high_staff_role(member: discord.Member) -> bool:
    return any(role.id in HIGH_STAFF_ROLE_IDS for role in member.roles)

def has_owner_role(member: discord.Member) -> bool:
    return any(role.id in OWNER_ROLE_IDS for role in member.roles)

def has_capt_manage_role(member: discord.Member) -> bool:
    return has_owner_role(member) or has_high_staff_role(member)

def has_ticket_close_role(member: discord.Member) -> bool:
    return any(role.id in TICKET_CLOSE_ROLE_IDS for role in member.roles)

def get_next_penalty_role(member: discord.Member) -> discord.Role | None:
    guild = member.guild

    penalty_roles = [
        guild.get_role(rid)
        for rid in PENALTY_ROLE_IDS
        if guild.get_role(rid)
    ]
    
    current_index = -1
    for i, role in enumerate(penalty_roles):
        if role in member.roles:
            current_index = i

    if current_index + 1 >= len(penalty_roles):
        return None

    return penalty_roles[current_index + 1]

def get_user_id_from_embed(embed: discord.Embed) -> int | None:
    try:
        if embed.footer and embed.footer.text:
            txt = embed.footer.text.strip()
            if "user_id:" in txt:
                return int(txt.split("user_id:", 1)[1].strip())
            if "id:" in txt:
                return int(txt.split("id:", 1)[1].strip())
    except:
        pass

    for field in embed.fields:
        if "ID:" in field.value:
            try:
                return int(field.value.split("ID:", 1)[1].strip())
            except:
                return None

    return None


# ================== ACTIVITY REPORT STATE ==================

LAST_ACTIVITY_REPORT = {}
WAITING_FOR_ACTIVITY = {}
WAITING_FOR_ROLLBACK = {}
WAITING_FOR_ANALYZE = set()
WAITING_FOR_APPEAL_PROOF = {}
MEETING_MANUAL_PRESENT = set()

# ================== DATA ==================

ic_vacations = {}  # user_id -> {"until": datetime, "approved_by": moderator_id}

# ================== VOICE ACTIVITY ==================

voice_sessions = {}
# user_id -> {
#   "channel_id": int,
#   "joined_at": datetime
# }

daily_voice_time = {}
# user_id -> seconds

# ================== SOBRANIE OTPUSK ==================


MEETING_ABSENCE_THREAD_NAME = "Отсутствие на собрании"

async def get_meeting_absence_thread(channel: discord.TextChannel):
    for thread in channel.threads:
        if thread.name == MEETING_ABSENCE_THREAD_NAME:
            return thread

    async for thread in channel.archived_threads():
        if thread.name == MEETING_ABSENCE_THREAD_NAME:
            return thread

    return await channel.create_thread(
        name=MEETING_ABSENCE_THREAD_NAME,
        type=discord.ChannelType.public_thread
    )




# ================== ROLLBACK DATA ==================

ROLLBACK_REQUESTS = {}
not_found = []


# ================== DISCORD ==================

#intents = discord.Intents.all()
#intents = discord.Intents.default()
#intents.members = True
#intents.message_content = True
#intents.voice_states = True
#bot = Bot(intents=intents)

CAPT_DATA = {}
WAITING_FOR_CAPT_SCREENSHOT = {}

#CAPT_DATA = {
    #capt_id: {
        #"time": str,
        #"group_code": str,
        #"screenshot_url": str,

        #"applied": set(),   # подавшие
        #"main": set(),      # основной состав
        #"reserve": set(),   # замена

        #"war_message_id": int,
        #"list_message_id": int,
    #}
#}


# ================== IC THREAD ==================

IC_THREAD_NAME = "IC-отпуска"

async def get_ic_thread(channel: discord.TextChannel):
    for thread in channel.threads:
        if thread.name == IC_THREAD_NAME:
            return thread

    async for thread in channel.archived_threads():
        if thread.name == IC_THREAD_NAME:
            return thread

    return await channel.create_thread(
        name=IC_THREAD_NAME,
        type=discord.ChannelType.public_thread
    )

# ================== OCR UTILS ==================

def get_activity_data_from_reply(message: discord.Message) -> dict | None:
    if not message.reference or not message.reference.message_id:
        return None

    report_msg_id = message.reference.message_id
    data = ACTIVITY_REPORTS.get(report_msg_id)
    if not data:
        return None

    if "channel_id" not in data:
        data["channel_id"] = message.reference.channel_id or message.channel.id

    return data

def normalize_name_full(name: str) -> str:
    name = name.lower().replace("_", " ")
    name = re.sub(r"[^a-z ]", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name

def discord_to_game_key(display_name: str) -> str:
    if "|" in display_name:
        display_name = display_name.split("|", 1)[1].strip()
    return normalize_character_name(display_name)

def game_to_key(name: str) -> str:
    return normalize_character_name(fix_ocr_prefix(name))

def fix_ocr_prefix(name: str) -> str:
    name = name.strip()
    if len(name) >= 2 and name[0] in ("i", "I"):
        if name[1].isalpha():
            return name[1:]
    return name

def clean_player_name(text: str) -> str:
    text = re.sub(r"^[✅❌✈️]\s*", "", text)
    text = re.sub(r"\s*\(до .*?\)", "", text)
    return text.strip()


def normalize_name(name: str) -> str:
    name = name.lower().replace("_", " ")
    name = re.sub(r"[^a-z ]", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name.split(" ")[0] if name else ""

def names_match(discord_name: str, game_name: str) -> bool:
    if "|" in discord_name:
        discord_name = discord_name.split("|", 1)[1].strip()

    a = normalize_name(discord_name)
    b = normalize_name(game_name)

    if not a or not b:
        return False

    return a == b

def clean_player_name(text: str) -> str:
    text = re.sub(r"^[✅❌✈️]\s*", "", text)
    text = re.sub(r"\s*\(до .*?\)", "", text)

    return text.strip()

def normalize_character_name(text: str) -> str:
    text = text.lower().strip()

    if "|" in text:
        text = text.split("|", 1)[1]

    text = text.split()[0]

    text = re.sub(r"[^a-zа-я]", "", text)

    return text

def dedup_game_names(raw_names: set[str]) -> list[str]:
    best: dict[str, str] = {}

    for s in raw_names:
        s = re.sub(r"\s+", " ", s).strip()    
        s = fix_ocr_prefix(s)                 
        key = normalize_character_name(s)      

        if not key:
            continue

        if key not in best or len(s) > len(best[key]):
            best[key] = s

    return sorted(best.values(), key=lambda x: normalize_character_name(x))

def extract_game_names(image_path: str) -> set[str]:
    img = cv2.imread(image_path)
    img = cv2.resize(img, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    results = set()

    for processed in [gray, cv2.bitwise_not(gray)]:
        thresh = cv2.adaptiveThreshold(
            processed, 255,
            cv2.ADAPTIVE_THRESH_MEAN_C,
            cv2.THRESH_BINARY,
            15, 3
        )

        text = pytesseract.image_to_string(
            thresh,
            config="--psm 6",
            lang="eng"
        )

        for line in text.splitlines():
            clean = re.sub(r"[^A-Za-z ]", "", line).strip()
            clean = fix_ocr_prefix(clean)
            if len(clean.split()) >= 2:
                results.add(clean)

    return results

def numbered_list(items: list[str]) -> str:
    if not items:
        return "—"
    return "\n".join(f"{i+1}. {item}" for i, item in enumerate(items))

def split_to_embed_fields(embed: discord.Embed, title: str, items: list[str], prefix_icon: str):
    if not items:
        embed.add_field(name=title, value="—", inline=False)
        return

    lines = [f"{i+1}. {prefix_icon} {name}" for i, name in enumerate(items)]
    chunk = []
    cur_len = 0
    part = 1

    def flush():
        nonlocal part, chunk, cur_len
        if not chunk:
            return
        name = title if part == 1 else f"{title} (продолжение)"
        embed.add_field(name=name, value="\n".join(chunk)[:1024], inline=False)
        part += 1
        chunk = []
        cur_len = 0

    for line in lines:
        add_len = len(line) + 1
        if cur_len + add_len > 1000:
            flush()
        chunk.append(line)
        cur_len += add_len

    flush()


def split_embed_field(text: str, limit: int = 1024):
    if not text:
        return ["-"]
    lines = text.split("\n")
    chunks = []
    current = ""

    for line in lines:
        if len(current) + len(line) + 1 > limit:
            chunks.append(current or "-")
            current = line
        else:
            current += ("\n" if current else "") + line
    if current:
        chunks.append(current)
    return chunks

def build_capt_list_embed(guild: discord.Guild, capt_id: int):
    data = CAPT_DATA[capt_id]

    def fmt(users: dict[int, str | None], sort=False):
        if not users:
            return "—", []

        lines = []
        ordered_ids = []

        items = sort_main_by_tier(guild, users) if sort else users.items()

        index = 1
        for uid, comment in items:
            member = guild.get_member(uid)
            if not member:
                continue

            tier = get_user_tier(member)
            tag = {
                "tier1": "💪",
                "owner": "🥇",
                "tier2": "🥈",
                "tier3": "🥉"
            }.get(tier, "👤")

            line = f"{index}. {tag} {member.mention}"
            if comment:
                line += f" — {comment}"

            lines.append(line)
            ordered_ids.append(uid)
            index += 1

        if not lines:
            return "—", []

        return "\n".join(lines), ordered_ids

    embed = discord.Embed(
        title="📋 Список на капт",
        color=discord.Color.blue()
    )
    embed.set_image(url="https://media.discordapp.net/attachments/675341437336027166/1014634234444521583/alliance2.gif")

    main_text, main_ids = fmt(data["main"], sort=True)
    for i, chunk in enumerate(split_embed_field(main_text)):
        embed.add_field(
            name="🟢 Основной состав" if i == 0 else " ",
            value=chunk,
            inline=False
        )

    reserve_text, reserve_ids = fmt(data["reserve"], sort=False)
    for i, chunk in enumerate(split_embed_field(reserve_text)):
        embed.add_field(
            name="🟡 Замена" if i == 0 else " ",
            value=chunk,
            inline=False
        )

    embed.set_footer(
        text=f"capt_id:{capt_id};main:{','.join(map(str, main_ids))};reserve:{','.join(map(str, reserve_ids))}"
    )
    return embed


def sort_main_by_tier(guild: discord.Guild, main_dict: dict[int, str | None]):
    def priority(uid):
        member = guild.get_member(uid)
        if not member:
            return 99

        tier = get_user_tier(member)
        return {
            "tier1": 1,
            "owner": 2,
            "tier2": 3,
            "tier3": 4
        }.get(tier, 3)

    return sorted(main_dict.items(), key=lambda x: priority(x[0]))

def activity_key(s: str) -> str:
    s = clean_player_name(s)
    s = re.sub(r"^\s*\d+\.\s*", "", s)
    s = s.strip()

    s = re.sub(r"[^a-zа-я| ]", " ", s.lower())
    s = re.sub(r"\s+", " ", s).strip()

    if "|" in s:
        s = s.split("|", 1)[1].strip()

    parts = s.split()
    if not parts:
        return ""

    if len(parts) >= 2 and len(parts[0]) == 1:
        return parts[1]

    return parts[0]

def remove_name_from_list(lst: list[str], key: str) -> bool:
    for i, item in enumerate(lst):
        if activity_key(item) == key:
            lst.pop(i)
            return True
    return False

def remove_by_index(lst: list[str], idx: int) -> bool:
    if idx < 1 or idx > len(lst):
        return False
    lst.pop(idx - 1)
    return True

def replace_name_in_list(lst: list[str], old_key: str, new_name: str) -> bool:
    for i, item in enumerate(lst):
        if activity_key(item) == old_key:
            prefix = ""
            m = re.match(r"^\s*([✅❌✈️])\s*", item)
            if m:
                prefix = m.group(1) + " "

            num = ""
            m2 = re.match(r"^\s*(\d+\.)\s*", item)
            if m2:
                num = m2.group(1) + " "

            lst[i] = f"{num}{prefix}{new_name}".strip()
            return True
    return False

def replace_name_by_index(lst: list[str], idx: int, new_name: str) -> bool:
    if idx < 1 or idx > len(lst):
        return False

    old_item = lst[idx - 1]

    prefix = ""
    m = re.match(r"^\s*([✅❌✈️])\s+", old_item)
    if m:
        prefix = m.group(1) + " "

    lst[idx - 1] = f"{prefix}{new_name}".strip()
    return True

async def refresh_activity_report_by_id(
    channel: discord.TextChannel,
    report_message_id: int,
    data: dict
):
    try:
        msg = await channel.fetch_message(report_message_id)
    except discord.NotFound:
        return

    embed = build_activity_embed(data)
    await msg.edit(embed=embed)

async def handle_activity_fix_command(message: discord.Message) -> bool:
    if message.guild is None:
        return False
    if message.channel.id != ACTIVITY_REPORT_CHANNEL_ID:
        return False
    if not has_high_staff_role(message.author):
        return False

    data = get_activity_data_from_reply(message)
    if not data:
        await message.reply("❌ Используй команду ответом (Reply) на сообщение отчёта актива.", delete_after=8)
        return True

    txt = message.content.strip()

    m = FIX_BY_INDEX_RE.match(txt)
    if m:
        where = m.group(1).lower()
        idx = int(m.group(2))
        new_name = m.group(3).strip()

        list_key = LIST_KEY_MAP[where]
        ok = replace_name_by_index(data[list_key], idx, new_name)
        if not ok:
            await message.reply("❌ Неверный номер", delete_after=6)
            return True

        await refresh_activity_report_by_id(message.channel, data["message_id"], data)
        await _silent_ack(message)
        return True

    m = DELETE_BY_INDEX_RE.match(txt)
    if m:
        where = m.group(1).lower()
        idx = int(m.group(2))

        list_key = LIST_KEY_MAP[where]
        ok = remove_by_index(data[list_key], idx)
        if not ok:
            await message.reply("❌ Неверный номер", delete_after=6)
            return True

        await refresh_activity_report_by_id(message.channel, data["message_id"], data)
        await _silent_ack(message)
        return True

    return False


async def _silent_ack(message: discord.Message):
    try:
        await message.delete()
    except:
        pass


async def refresh_activity_report(data: dict, guild: discord.Guild, fallback_channel_id: int | None = None):
    channel_id = data.get("channel_id") or fallback_channel_id
    if not channel_id:
        return

    channel = guild.get_channel(channel_id)
    if not channel:
        return

    try:
        msg = await channel.fetch_message(data["message_id"])
    except discord.NotFound:
        return

    await msg.edit(embed=build_activity_embed(data))

def get_voice_names_from_channel(channel: discord.VoiceChannel, required_left: str | None) -> set[str]:
    names = set()

    for member in channel.members:
        if member.bot:
            continue
        if "|" not in member.display_name:
            continue

        left, right = member.display_name.split("|", 1)
        left = left.strip()
        right = right.strip()

        if required_left is not None and left.lower() != required_left.lower():
            continue

        if right:
            names.add(right)

    return names

def get_voice_guild_candidates(bot: discord.Client, origin_guild: discord.Guild):
    cfg = GUILD_CONFIG.get(origin_guild.id, {})
    mode = cfg.get("ACTIVITY_VOICE_SOURCE", "self")

    ally_guild = bot.get_guild(ALLY_GUILD_ID)

    if mode == "self":
        return [(origin_guild, cfg.get("SELF_REQUIRED_LEFT"))]

    if mode == "ally":
        return ([(ally_guild, cfg.get("ALLY_REQUIRED_LEFT"))] if ally_guild else [])

    out = [(origin_guild, cfg.get("SELF_REQUIRED_LEFT"))]
    if ally_guild:
        out.append((ally_guild, cfg.get("ALLY_REQUIRED_LEFT")))
    return out


def get_largest_voice_channel_multi(bot: discord.Client, origin_guild: discord.Guild):
    candidates = get_voice_guild_candidates(bot, origin_guild)

    best_channel = None
    best_required_left = None
    best_count = 0

    for g, required_left in candidates:
        if not g:
            continue

        for vc in g.voice_channels:
            count = len([m for m in vc.members if not m.bot])
            if count > best_count:
                best_channel = vc
                best_required_left = required_left
                best_count = count

    return best_channel, best_required_left

def numbered_lines(items: list[str]) -> list[str]:
    return [f"{i+1}. {item}" for i, item in enumerate(items)]

def build_activity_embed(data):
    embed = discord.Embed(
        title="Отчёт актива",
        description=(
            f"**Комментарий:**\n{data['comment']}\n\n"
            f"**Запрашивающий:**\n<@{data['requested_by']}>\n\n"
            f"**Игроков на скриншоте:** {data['players_total']}\n"
            f"**В голосовом канале:** {data['voice_count']}\n"
            f"**Канал:** {data['voice_channel']}"
        ),
        color=discord.Color.green(),
        timestamp=data["created_at"]
    )

    split_to_embed_fields(embed, f"✅ В игре и в войсе ({len(data['both'])})", data["both"], "✅")
    split_to_embed_fields(embed, f"❌ В игре, но не в войсе ({len(data['not_voice'])})", data["not_voice"], "❌")
    split_to_embed_fields(embed, f"✈️ IC-отпуск ({len(data['ic'])})", data["ic"], "✈️")

    return embed

def get_next_penalty_role(member: discord.Member):
    """
    Возвращает (next_role, old_role)
    Если штраф максимальный — (None, None)
    """

    guild = member.guild

    penalty_roles = [
        guild.get_role(rid)
        for rid in PENALTY_ROLE_IDS
        if guild.get_role(rid)
    ]

    member_penalties = [
        r for r in penalty_roles if r in member.roles
    ]

    if not member_penalties:

        return penalty_roles[0], None

    current = max(
        member_penalties,
        key=lambda r: penalty_roles.index(r)
    )

    idx = penalty_roles.index(current)

    if idx + 1 >= len(penalty_roles):
        return None, None

    return penalty_roles[idx + 1], current



def ticket_name_from_player(name: str) -> str:
    return name.lower().replace(" ", "-")

def find_ticket_by_player(guild: discord.Guild, player_name: str):
    target = normalize_character_name(player_name)
    if not target:
        return None

    for channel in guild.channels:
        if not isinstance(channel, discord.TextChannel):
            continue
        if channel.category_id not in PLAYER_TICKET_CATEGORY_IDS:
            continue

        parts = channel.name.lower().split("-")

        if target in parts:
            return channel

        if len(target) >= 3 and any(target in p for p in parts):
            return channel

    return None



def build_voice_top_embed(guild):
    now = datetime.now(timezone.utc)
    temp_times = daily_voice_time.copy()

    for user_id, session in voice_sessions.items():
        joined_at = datetime.fromisoformat(session["joined_at"])
        delta = (now - joined_at).total_seconds()
        temp_times[int(user_id)] = temp_times.get(int(user_id), 0) + int(delta)

    sorted_users = sorted(temp_times.items(), key=lambda x: x[1], reverse=True)[:10]

    embed = discord.Embed(
        title="ТОП-10 по активности за день",
        color=discord.Color.blue(),
        timestamp=datetime.now(timezone.utc)
    )

    if not sorted_users:
        embed.description = "Нет данных"
        return embed

    lines = []
    for i, (user_id, seconds) in enumerate(sorted_users, start=1):
        member = guild.get_member(user_id)
        if not member:
            continue
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        lines.append(f"**{i}.** {member.display_name} — `{hours}ч {minutes}м {secs}с`")

    embed.description = "\n".join(lines)
    return embed



def build_meeting_absence_panel_embed():
    embed = discord.Embed(
        title="Отсутствие на собрании",
        description=(
            "Если вы **не можете присутствовать на собрании**, "
            "подайте заявку, указав причину.\n\n"
        ),
        color=discord.Color.orange()
    )
    embed.set_image(url="https://media.discordapp.net/attachments/675341437336027166/1014634234444521583/alliance2.gif?ex=697f1004&is=697dbe84&hm=a6d557da5d812193e658e2ce2624dcc77ed4c3569202d73e7e8d912d4be4f95c&")

    embed.set_footer(text="AllianceBot")

    return embed


# ================== BIRTHDAYS ==================

def load_birthdays():
    global BIRTHDAYS
    if not BIRTHDAYS_FILE.exists() or BIRTHDAYS_FILE.stat().st_size == 0:
        BIRTHDAYS = {}
        BIRTHDAYS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(BIRTHDAYS_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f, ensure_ascii=False, indent=2)
        return

    with open(BIRTHDAYS_FILE, "r", encoding="utf-8") as f:
        BIRTHDAYS = json.load(f) or {}

def save_birthdays():
    BIRTHDAYS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(BIRTHDAYS_FILE, "w", encoding="utf-8") as f:
        json.dump(BIRTHDAYS, f, ensure_ascii=False, indent=2)

def _ddmm_to_sortkey(ddmm: str):
    try:
        d, m = ddmm.split(".")
        return (int(m), int(d))
    except:
        return (99, 99)

def build_birthdays_embed(guild: discord.Guild) -> discord.Embed:
    embed = discord.Embed(
        title="Дни рождения",
        description="Нажми кнопку ДР в панели и введи дату в формате **ДД.ММ**",
        color=discord.Color.pink()
    )

    if not BIRTHDAYS:
        embed.add_field(name="Список", value="—", inline=False)
        return embed

    lines = []
    for uid_str, ddmm in sorted(BIRTHDAYS.items(), key=lambda x: _ddmm_to_sortkey(x[1])):
        uid = int(uid_str)
        member = guild.get_member(uid)
        mention = member.mention if member else f"<@{uid}>"
        lines.append(f"• {ddmm} — {mention}")

    chunks = []
    cur = ""
    for line in lines:
        if len(cur) + len(line) + 1 > 1000:
            chunks.append(cur)
            cur = line
        else:
            cur += ("\n" if cur else "") + line
    if cur:
        chunks.append(cur)

    for i, ch in enumerate(chunks):
        embed.add_field(name="Список" if i == 0 else " ", value=ch, inline=False)

    return embed

async def ensure_birthdays_list_message(bot: discord.Client, guild: discord.Guild):
    ch = guild.get_channel(BIRTHDAY_STAFF_CHANNEL_ID)
    if not ch:
        return

    async for msg in ch.history(limit=30):
        if msg.author and msg.author.id == bot.user.id and msg.embeds:
            emb = msg.embeds[0]
            if emb.title and "Дни рождения" in emb.title:
                await msg.edit(embed=build_birthdays_embed(guild))
                return

    await ch.send(embed=build_birthdays_embed(guild))

class BirthdayModal(discord.ui.Modal, title="🎂 Указать день рождения"):
    date = discord.ui.TextInput(
        label="Дата (ДД.ММ)",
        placeholder="28.01",
        required=True,
        max_length=5
    )

    async def on_submit(self, interaction: discord.Interaction):
        raw = self.date.value.strip()
        m = BIRTHDAY_DATE_RE.match(raw)
        if not m:
            return await interaction.response.send_message("❌ Формат неверный. Нужно ДД.ММ (пример: 28.01)", ephemeral=True)

        dd = int(m.group(1))
        mm = int(m.group(2))

        if not (1 <= mm <= 12):
            return await interaction.response.send_message("❌ Месяц должен быть 01..12", ephemeral=True)
        if not (1 <= dd <= 31):
            return await interaction.response.send_message("❌ День должен быть 01..31", ephemeral=True)

        BIRTHDAYS[str(interaction.user.id)] = f"{dd:02d}.{mm:02d}"
        save_birthdays()

        await interaction.response.send_message(f"✅ Сохранено: **{dd:02d}.{mm:02d}**", ephemeral=True)

        await ensure_birthdays_list_message(interaction.client, interaction.guild)


class BirthdayPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="ДР", style=discord.ButtonStyle.primary, custom_id="birthday_set")
    async def birthday_set(self, interaction: discord.Interaction, _):
        await interaction.response.send_modal(BirthdayModal())

async def ensure_birthday_panel(bot: discord.Client, guild: discord.Guild):
    ch = guild.get_channel(BIRTHDAY_PANEL_CHANNEL_ID)
    if not ch:
        return

    async for msg in ch.history(limit=20):
        if msg.author.id == bot.user.id and msg.components:
            for row in msg.components:
                for comp in row.children:
                    if getattr(comp, "custom_id", None) == "birthday_set":
                        return

    embed = discord.Embed(
        title="Дни рождения",
        description="Нажми кнопку ДР и введи дату своего дня рождения в формате ДД.ММ.",
        color=discord.Color.pink()
    )
    embed.set_image(url="https://media.discordapp.net/attachments/675341437336027166/1014634234444521583/alliance2.gif?ex=697f1004&is=697dbe84&hm=a6d557da5d812193e658e2ce2624dcc77ed4c3569202d73e7e8d912d4be4f95c&")
    await ch.send(embed=embed, view=BirthdayPanelView())

async def birthday_daily_task(bot: discord.Client):
    await bot.wait_until_ready()

    while not bot.is_closed():
        try:
            now_msk = datetime.now(MSK)
            target = now_msk.replace(hour=9, minute=0, second=0, microsecond=0)
            if now_msk >= target:
                target += timedelta(days=1)

            await asyncio.sleep((target - now_msk).total_seconds())

            load_birthdays()

            today = datetime.now(MSK).strftime("%d.%m")

            for guild in bot.guilds:
                staff_ch = guild.get_channel(BIRTHDAY_STAFF_CHANNEL_ID)
                if not staff_ch:
                    continue

                uids = [int(uid) for uid, ddmm in BIRTHDAYS.items() if ddmm == today]
                if not uids:
                    continue

                high_staff_role_id = HIGH_STAFF_ROLE_IDS[0] if isinstance(HIGH_STAFF_ROLE_IDS, (list, tuple, set)) else HIGH_STAFF_ROLE_IDS 
                role = guild.get_role(high_staff_role_id)
                role_mention = role.mention if role else f"<@&{high_staff_role_id}>"

                people_mentions = " ".join(f"<@{uid}>" for uid in uids)

                await staff_ch.send(f"🎉 {role_mention} сегодня ДР у: {people_mentions}")

        except Exception as e:
            print("birthday_daily_task error:", repr(e))
            await asyncio.sleep(10)

# ================== SOBRANIE OTPUSK ==================

class MeetingAbsenceModal(discord.ui.Modal, title="Отсутствие на собрании"):
    reason = discord.ui.TextInput(
        label="Причина отсутствия",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=300
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        channel = interaction.client.get_channel(MEETING_PANEL_CHANNEL)
        if not channel:
            return await interaction.followup.send(
                "❌ Канал панели не найден",
                ephemeral=True
            )

        thread = await get_meeting_absence_thread(channel)

        embed = discord.Embed(
            title="Заявка на отсутствие",
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc)
        )

        embed.description = (
            f"**Игрок:** {interaction.user.mention}\n\n"
            f"**Причина:**\n{self.reason.value}"
        )

        embed.set_footer(text=f"absence_uid:{interaction.user.id}")

        embed.set_thumbnail(url=interaction.user.display_avatar.url)

        await thread.send(
            content=(
                f"{interaction.user.mention} отправил(а) заявку "
                f"<@&{DISCIPLINE_ROLE_ID}>"
            ),
            embed=embed,
            view=MeetingAbsenceApproveView()
        )

        await interaction.followup.send(
            "✅ Заявка отправлена",
            ephemeral=True
        )


class MeetingAbsenceApproveView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    def _get_absence_uid(self, message: discord.Message) -> int | None:
        embed = message.embeds[0] if message.embeds else None
        footer = embed.footer.text if (embed and embed.footer) else ""
        if not footer:
            return None

        if "absence_uid:" in footer:
            raw = footer.split("absence_uid:", 1)[1].strip()
            raw = raw.split()[0] 
            return int(raw) if raw.isdigit() else None

        return None

    def _get_reason_from_embed(self, message: discord.Message) -> str:
        embed = message.embeds[0] if message.embeds else None
        if not embed or not embed.description:
            return ""
        m = re.search(r"\*\*Причина:\*\*\s*\n(.+)$", embed.description, re.S)
        return m.group(1).strip() if m else ""

    def _disable_all(self):
        for item in self.children:
            item.disabled = True

    @discord.ui.button(
        label="Одобрить",
        style=discord.ButtonStyle.success,
        custom_id="meeting_absence_approve"
    )
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not has_high_staff_role(interaction.user):
            return await interaction.response.send_message("❌ Нет прав", ephemeral=True)

        uid = self._get_absence_uid(interaction.message)
        if not uid:
            return await interaction.response.send_message(
                "❌ Не найден absence_uid в сообщении (footer).",
                ephemeral=True
            )

        reason = self._get_reason_from_embed(interaction.message)

        MEETING_ABSENCE_DATA.setdefault("approved", {})
        MEETING_ABSENCE_DATA["approved"][str(self.user_id)] = self.reason

        embed = interaction.message.embeds[0] if interaction.message.embeds else discord.Embed()
        embed.color = discord.Color.green()
        embed.description = (embed.description or "") + (
            f"\n\n**Статус:** ✅ Одобрено"
            f"\n**Одобрил:** {interaction.user.display_name}"
        )

        self._disable_all()
        await interaction.message.edit(embed=embed, view=self)

        member = interaction.guild.get_member(uid) if interaction.guild else None
        if member:
            try:
                await member.send("✅ Ваша заявка на отсутствие на собрании одобрена")
            except discord.Forbidden:
                pass

        await interaction.response.send_message("✅ Одобрено", ephemeral=True)

    @discord.ui.button(
        label="Отклонить",
        style=discord.ButtonStyle.danger,
        custom_id="meeting_absence_reject"
    )
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not has_high_staff_role(interaction.user):
            return await interaction.response.send_message("❌ Нет прав", ephemeral=True)

        uid = self._get_absence_uid(interaction.message)
        if not uid:
            return await interaction.response.send_message(
                "❌ Не найден absence_uid в сообщении (footer).",
                ephemeral=True
            )

        await interaction.response.send_modal(
            MeetingAbsenceRejectModal(
                message=interaction.message,
                user_id=uid
            )
        )


class MeetingAbsenceRejectModal(discord.ui.Modal, title="Причина отклонения"):
    reason = discord.ui.TextInput(
        label="Причина",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=300
    )

    def __init__(self, message: discord.Message, user_id: int):
        super().__init__()
        self.message = message
        self.user_id = user_id

    async def on_submit(self, interaction: discord.Interaction):
        embed = self.message.embeds[0]
        embed.color = discord.Color.red()
        embed.description += (
            f"\n\n**Статус:** Отклонено"
            f"\n**Причина:** {self.reason.value}"
            f"\n**Отклонил:** {interaction.user.display_name}"
        )

        for item in self.message.components[0].children:
            item.disabled = True

        await self.message.edit(embed=embed)

        member = interaction.guild.get_member(self.user_id)
        if member:
            try:
                await member.send(
                    f"❌ Ваша заявка на отсутствие отклонена\n"
                    f"Причина: {self.reason.value}"
                )
            except discord.Forbidden:
                pass

        await interaction.response.send_message(
            "❌ Заявка отклонена",
            ephemeral=True
        )


class MeetingAbsencePanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Подать заявку",
        style=discord.ButtonStyle.primary,
        custom_id="meeting_absence_request"
    )
    async def request(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(MeetingAbsenceModal())



# ================== FAMILYWARMOVE ==================

class CaptMoveModal(discord.ui.Modal):
    def __init__(self, capt_id: int, action: str):
        super().__init__(title="Управление списком")
        self.capt_id = capt_id
        self.action = action

        self.user_input = discord.ui.TextInput(
            label="Укажите @пользователя или ID",
            required=True
        )
        self.add_item(self.user_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        data = CAPT_DATA[self.capt_id]

        raw = self.user_input.value.strip().replace("<@", "").replace(">", "")
        if not raw.isdigit():
            await interaction.followup.send("❌ Некорректный пользователь", ephemeral=True)
            return

        uid = int(raw)

        def pop_from_any():
            for key in ("main", "reserve", "applied"):
                if uid in data[key]:
                    return key, data[key].pop(uid)
            return None, None

        src, comment = pop_from_any()

        if src is None:
            await interaction.followup.send("❌ Игрок не найден", ephemeral=True)
            return

        if self.action == "to_main":

            if len(data["main"]) >= 35:
                await interaction.followup.send(
                    "Основной состав уже заполнен (35/35). Вы добавлены в **Замену**",
                    ephemeral=True
                )
                if src:
                    data[src][uid] = comment
                return
            data["main"][uid] = comment
            await notify(uid, "🟢 Вы перенесены в **Основной состав**")

        elif self.action == "to_reserve":
            data["reserve"][uid] = comment
            await notify(uid, "🟡 Вы перенесены в **Замены**")

        elif self.action == "from_main":
            if src != "main":
                await interaction.followup.send("❌ Игрок не в основном составе", ephemeral=True)
                return
            data["reserve"][uid] = comment
            await notify(uid, "🟡 Вы перенесены в **Замены**")

        await update_capt_list(interaction.guild, self.capt_id)

async def handle_capt_move_by_text(message: discord.Message) -> bool:
    if message.guild is None:
        return False
    if message.channel.id != FAMILY_SPISOK_CHANNEL:
        return False

    cmds = parse_capt_cmds(message.content)
    if not cmds:
        return False

    if not has_capt_manage_role(message.author):
        await message.reply("❌ Нет прав", delete_after=6)
        return True

    capt_id = get_active_capt_id_for_channel(message.channel.id)
    if not capt_id or capt_id not in CAPT_DATA:
        await message.reply("❌ Активный список капта не найден", delete_after=6)
        return True

    data = CAPT_DATA[capt_id]
    

    msg_id = data.get("list_message_id")
    if not msg_id:
        await message.reply("❌ Сообщение со списком не найдено", delete_after=6)
        return True

    try:
        list_msg = await message.channel.fetch_message(msg_id)
    except:
        await message.reply("❌ Сообщение со списком не найдено", delete_after=6)
        return True

    embed = list_msg.embeds[0] if list_msg.embeds else None
    footer_capt_id, main_ids, reserve_ids = parse_capt_footer(embed)

    if footer_capt_id is not None and footer_capt_id != capt_id:
        await message.reply("❌ Это сообщение списка относится к другому капту", delete_after=6)
        return True

    if not main_ids and not reserve_ids:
        await message.reply("❌ Не найден footer с порядком игроков. Обновите список.", delete_after=6)
        return True

    main_ids = [uid for uid in main_ids if uid in data["main"]]
    reserve_ids = [uid for uid in reserve_ids if uid in data["reserve"]]

    moved_to_main = 0
    moved_to_reserve = 0
    errors = 0
    blocked_full = 0

    for idx, sign in cmds:
        if sign == "+":
            if idx < 1 or idx > len(reserve_ids):
                errors += 1
                continue

            uid = reserve_ids[idx - 1]
            comment = data["reserve"].pop(uid, None)

            if len(data["main"]) >= 35:
                data["reserve"][uid] = comment
                blocked_full += 1
                continue

            data["main"][uid] = comment
            moved_to_main += 1
            reserve_ids.pop(idx - 1)
            main_ids.append(uid)
            await notify(uid, "🟢 Вы перенесены в Основной состав")

        elif sign == "-":
            if idx < 1 or idx > len(main_ids):
                errors += 1
                continue

            uid = main_ids[idx - 1]
            comment = data["main"].pop(uid, None)

            data["reserve"][uid] = comment
            moved_to_reserve += 1
            main_ids.pop(idx - 1)
            reserve_ids.append(uid)
            await notify(uid, "🟡 Вы перенесены в Замены")

    await update_capt_list(message.guild, capt_id)

    try:
        await message.delete()
    except:
        pass

    if moved_to_main or moved_to_reserve or errors or blocked_full:
        parts = []
        if moved_to_main:
            parts.append(f"+{moved_to_main}")
        if moved_to_reserve:
            parts.append(f"-{moved_to_reserve}")
        if blocked_full:
            parts.append(f"main full: {blocked_full}")
        if errors:
            parts.append(f"errors: {errors}")
        await message.channel.send("🧩 " + ", ".join(parts), delete_after=6)

    return True

async def notify(user_id: int, text: str):
    user = bot.get_user(user_id)
    if user:
        try:
            await user.send(text)
        except:
            pass

class CaptRollbackRequestModal(discord.ui.Modal, title="Запрос откатов"):
    comment = discord.ui.TextInput(
        label="Комментарий",
        placeholder="откат vs Faraday 21.01 17:54",
        required=True,
        max_length=200
    )

    def __init__(self, capt_id: int):
        super().__init__()
        self.capt_id = capt_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        data = CAPT_DATA.get(self.capt_id)
        if not data:
            await interaction.followup.send("❌ Капт не найден", ephemeral=True)
            return

        if not data.get("main"):
            await interaction.followup.send("❌ В основном составе никого нет", ephemeral=True)
            return

        comment = self.comment.value.strip()

        sent, missed = await send_rollback_requests_for_capt(
            guild=interaction.guild,
            capt_id=self.capt_id,
            comment=comment,
            requested_by=interaction.user.id
        )

        text = (
            f"Запрос откатов отправлен.\n\n"
            f"Комментарий:\n> {comment}\n\n"
            f"Успешно: {sent}\n"
            f"Тикеты не найдены: {missed}"
        )
        await interaction.followup.send(text, ephemeral=True)

class CaptManageView(discord.ui.View):
    def __init__(self, capt_id: int):
        super().__init__(timeout=None)
        self.capt_id = capt_id

    def staff_check(self, interaction):
        return has_capt_manage_role(interaction.user)

    @discord.ui.button(
        label="🔄 Запрос откатов",
        style=discord.ButtonStyle.primary,
        custom_id="capt_rollback_request"
    )
    async def capt_rollback_request(self, interaction: discord.Interaction, _):
        if not (has_owner_role(interaction.user) or has_high_staff_role(interaction.user)):
            return await interaction.response.send_message("❌ Нет прав", ephemeral=True)

        await interaction.response.send_modal(CaptRollbackRequestModal(self.capt_id))

    @discord.ui.button(label="🔒 Закрыть список", style=discord.ButtonStyle.danger)
    async def close(self, interaction, button: discord.ui.Button):
        if not self.staff_check(interaction):
            return await interaction.response.send_message("❌ Нет прав", ephemeral=True)

        await interaction.response.defer(ephemeral=True)

        data = CAPT_DATA[self.capt_id]
        data["closed"] = True

        for uid in data["main"]:
            await notify(uid, "🔒 Список закрыт. Вы участвуете в капте.")

        button.disabled = True

        await interaction.message.edit(view=self)
        await interaction.followup.send("🔒 Список закрыт", ephemeral=True)



# ================== FAMILYWAR ==================


class CaptStartModal(discord.ui.Modal, title="Начало капта"):
    start_time = discord.ui.TextInput(label="Время начала капта")
    group_code = discord.ui.TextInput(label="Код группы")

    async def on_submit(self, interaction: discord.Interaction):
        WAITING_FOR_CAPT_SCREENSHOT[interaction.user.id] = {
            "time": self.start_time.value,
            "group_code": self.group_code.value
        }

        await interaction.response.send_message(
            "📸 Отправьте **скриншот квадрата** следующим сообщением.",
            ephemeral=True
        )

async def send_capt_war_embed(guild, capt_id):
    data = CAPT_DATA[capt_id]
    channel = guild.get_channel(FAMILY_WAR_CHANNEL)

    file: discord.File = data["file"]

    embed = discord.Embed(
        title="⚔️ КАПТ",
        description=(
            f"🕒 **Время**\n {data['time']}\n"
            f"🔑 **Код группы**\n {data['group_code']}"
        ),
        color=discord.Color.red()
    )

    embed.set_image(url=f"attachment://{file.filename}")

    msg = await channel.send(
        content="@everyone",
        embed=embed,
        file=file,
        view=CaptJoinView(capt_id)
    )

    data["war_message_id"] = msg.id





async def ensure_capt_panel(bot: discord.Client):
    channel = bot.get_channel(FAMILY_WAR_PANEL_CHANNEL)
    if not channel:
        return

    async for msg in channel.history(limit=20):
        if msg.author.id == bot.user.id and msg.components:
            for row in msg.components:
                for comp in row.children:
                    if comp.custom_id == "capt_start":
                        return

    embed = discord.Embed(
        title="⚔️ Панель каптов",
        description="Нажмите кнопку ниже для создания капта",
        color=discord.Color.red()
    )
    embed.set_image(url="https://media.discordapp.net/attachments/675341437336027166/1014634234444521583/alliance2.gif?ex=697f1004&is=697dbe84&hm=a6d557da5d812193e658e2ce2624dcc77ed4c3569202d73e7e8d912d4be4f95c&")
    await channel.send(
        embed=embed,
        view=CaptPanelView()
    )

class CaptPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="⚔️ Капт",
        style=discord.ButtonStyle.danger,
        custom_id="capt_start"
    )
    async def start_capt(self, interaction: discord.Interaction, _):
        await interaction.response.send_modal(CaptStartModal())



async def send_capt_list_embed(guild: discord.Guild, capt_id: int):
    channel = guild.get_channel(FAMILY_SPISOK_CHANNEL)
    if not channel:
        return

    embed = build_capt_list_embed(guild, capt_id)

    msg = await channel.send(
        embed=embed,
        view=CaptManageView(capt_id)
    )

    CAPT_DATA[capt_id]["list_message_id"] = msg.id
    CAPT_DATA[capt_id]["spisok_channel_id"] = channel.id



async def update_capt_list(guild: discord.Guild, capt_id: int):
    data = CAPT_DATA.get(capt_id)
    if not data:
        return

    channel = guild.get_channel(FAMILY_SPISOK_CHANNEL)
    if not channel:
        return

    msg_id = data.get("list_message_id")
    if not msg_id:
        return

    embed = build_capt_list_embed(guild, capt_id)

    msg = channel.get_partial_message(msg_id)
    try:
        await msg.edit(embed=embed)
    except discord.NotFound:
        return
    except discord.HTTPException:
        return

def get_active_capt_id_for_channel(channel_id: int) -> int | None:
    candidates = []

    for capt_id, d in CAPT_DATA.items():
        if d.get("list_message_id") and d.get("spisok_channel_id") == channel_id:
            candidates.append(capt_id)

    if not candidates:
        return None

    return max(
        candidates,
        key=lambda cid: CAPT_DATA[cid].get("created_at") or str(cid)
    )



class CaptJoinView(discord.ui.View):
    def __init__(self, capt_id):
        super().__init__(timeout=None)
        self.capt_id = capt_id

    async def interaction_check(self, interaction: discord.Interaction):
        if CAPT_DATA[self.capt_id].get("closed"):
            await interaction.response.send_message(
                "🔒 Список уже закрыт",
                ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Записаться", style=discord.ButtonStyle.success)
    async def join(self, interaction, _):
        await interaction.response.send_modal(
            CaptJoinModal(self.capt_id)
        )

    @discord.ui.button(label="Выписаться", style=discord.ButtonStyle.danger)
    async def leave(self, interaction, _):
        await interaction.response.defer(ephemeral=True)

        data = CAPT_DATA[self.capt_id]
        uid = interaction.user.id

        data["applied"].pop(uid, None)
        data["main"].pop(uid, None)
        data["reserve"].pop(uid, None)

        await update_capt_list(interaction.guild, self.capt_id)

        await interaction.followup.send("❌ Вы выписались", ephemeral=True)

class CaptJoinModal(discord.ui.Modal, title="Запись на капт"):
    comment = discord.ui.TextInput(
        label="Комментарий (необязательно)",
        required=False
    )

    def __init__(self, capt_id):
        super().__init__()
        self.capt_id = capt_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        comment = self.comment.value.strip() or None
        data = CAPT_DATA[self.capt_id]
        uid = interaction.user.id

        for key in ("main", "reserve", "applied"):
            data[key].pop(uid, None)

        tier = get_user_tier(interaction.user)

        if tier and len(data["main"]) < 35:
            data["main"][uid] = comment
            await notify(
                uid,
                f"🟢 Вы добавлены в **Основной состав ({tier.upper()})**"
            )
        else:

            data["reserve"][uid] = comment
            await notify(
                uid,
                "🟡 Вы добавлены в **Замену**"
            )

        await update_capt_list(interaction.guild, self.capt_id)
        await interaction.followup.send("✅ Заявка принята", ephemeral=True)









# ================== IC MODAL ==================

class RollbackRequestModal(discord.ui.Modal, title="Запрос откатов"):

    comment = discord.ui.TextInput(
        label="Комментарий",
        placeholder="откат vs Faraday 08.12 19:35",
        required=True
    )

    async def on_submit(self, interaction):

        comment = self.comment.value.strip()

        WAITING_FOR_ROLLBACK[interaction.user.id] = comment

        await interaction.response.send_message(
            f"✅ **Запрос отката создан**\n\n"
            f"📝 **Комментарий:**\n> {comment}\n\n"
            "📸 Отправьте скриншоты следующим сообщением.\n"
            "Можно несколько.",
            ephemeral=True
        )


class ActivityRequestModal(discord.ui.Modal, title="Запрос актива"):

    comment = discord.ui.TextInput(
        label="Комментарий",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=500
    )

    async def on_submit(self, interaction: discord.Interaction):

        WAITING_FOR_ACTIVITY[interaction.user.id] = {
            "comment": self.comment.value
        }

        await interaction.response.send_message(
            "📸 Теперь отправьте **скриншот** следующим сообщением.",
            ephemeral=True
        )

class DisciplinePanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="📊 Запрос актива",
        style=discord.ButtonStyle.success,
        custom_id="discipline_activity"
    )
    async def activity(self, interaction, button):
        await interaction.response.send_modal(ActivityRequestModal())

    @discord.ui.button(
        label="📈 Анализ откатов",
        style=discord.ButtonStyle.secondary,
        custom_id="discipline_analyze"
    )
    async def rollback_analyze(self, interaction, button):
        WAITING_FOR_ANALYZE.add(interaction.user.id)

        analyze_channel = interaction.guild.get_channel(ANALYZE_CHANNEL_ID)

        if not analyze_channel:
            await interaction.response.send_message(
                "❌ Канал анализа не найден",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            f"📝 Напишите комментарий отката в канал {analyze_channel.mention}",
            ephemeral=True
        )

    @discord.ui.button(
        label="🏆 ТОП войса сейчас",
        style=discord.ButtonStyle.primary,
        custom_id="discipline_voice_top_now"
    )
    async def voice_top_now(self, interaction: discord.Interaction, button):

        embed = build_voice_top_embed(interaction.guild)

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )

    @discord.ui.button(
        label="🎤 Собрание",
        style=discord.ButtonStyle.danger,
        custom_id="discipline_meeting"
    )
    async def meeting(self, interaction: discord.Interaction, button):
        report_channel = interaction.guild.get_channel(ACTIVITY_REPORT_CHANNEL_ID)

        if not report_channel:
            await interaction.response.send_message(
                "❌ Канал отчетов не найден",
                ephemeral=True
            )
            return
            
        embed = build_meeting_embed(interaction.guild)
        report_channel = interaction.guild.get_channel(ACTIVITY_REPORT_CHANNEL_ID)
        reset_meeting_data()
        msg = await report_channel.send(
            embed=build_meeting_embed(interaction.guild),
            view=MeetingPunishView()
        )

        MEETING_ABSENCE_DATA["report_message_id"] = msg.id

        await interaction.response.send_message(
            f"✅ Отчет о собрании отправлен!\n🔗 Перейти к отчету: {msg.jump_url}",
            ephemeral=True
        )



class ICVacationModal(discord.ui.Modal, title="IC-отпуск"):
    duration = discord.ui.TextInput(
        label="Длительность (в минутах)",
        placeholder="Например: 30, 90",
        required=True
    )
    reason = discord.ui.TextInput(
        label="Причина",
        style=discord.TextStyle.paragraph,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        if not self.duration.value.isdigit():
            await interaction.followup.send("❌ Длительность должна быть числом", ephemeral=True)
            return

        channel = interaction.client.get_channel(IC_REQUEST_CHANNEL_ID)
        thread = await get_ic_thread(channel)

        embed = discord.Embed(
            title="Новая заявка!",
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.description = (
            f"**{interaction.user.display_name}**\n\n"
            f"**Причина**\n"
            f"{self.reason.value}\n\n"
            f"**Длительность**\n"
            f"{self.duration.value} минут"
        )

        embed.set_thumbnail(
            url=interaction.user.display_avatar.url
        )
        embed.set_footer(
            text=f"user_id:{interaction.user.id};duration:{self.duration.value}"
        )

        await thread.send(
            content=(
                f"{interaction.user.mention} отправил(а) заявку "
                f"<@&{DISCIPLINE_ROLE_ID}>"
            ),
            embed=embed,
            view=ICApproveView()
        )

        await interaction.followup.send("✅ Заявка отправлена", ephemeral=True)

# ================== APPROVE PENALTY ==================

class AppealWithProofModal(discord.ui.Modal, title="Обжалование наказания"):

    justification = discord.ui.TextInput(
        label="Почему вы не согласны с наказанием?",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=1000
    )

    def __init__(self, punished_member_id: int, message_link: str):
        super().__init__()
        self.punished_member_id = punished_member_id
        self.message_link = message_link

    async def on_submit(self, interaction: discord.Interaction):

        WAITING_FOR_APPEAL_PROOF[interaction.user.id] = {
            "justification": self.justification.value,
            "message_link": self.message_link
        }

        await interaction.response.send_message(
            "📎 Отправьте **доказательства следующим сообщением**.\n"
            "Можно несколько изображений.",
            ephemeral=True
        )


class AppealModal(discord.ui.Modal, title="Обжалование наказания"):

    justification = discord.ui.TextInput(
        label="Почему вы не согласны со штрафом?",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=1000
    )

    def __init__(self, message_link: str):
        super().__init__()
        self.message_link = message_link

    async def on_submit(self, interaction: discord.Interaction):

        guild = interaction.guild

        owner_roles = [
            guild.get_role(rid)
            for rid in OWNER_ROLE_IDS
            if guild.get_role(rid)
        ]

        roles_ping = " ".join(r.mention for r in owner_roles)

        embed = discord.Embed(
            title="Обжалование наказания",
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc)
        )

        embed.add_field(
            name="Игрок",
            value=f"{interaction.user.mention}",
            inline=False
        )

        embed.add_field(
            name="Оправдание",
            value=self.justification.value,
            inline=False
        )

        embed.add_field(
            name="Сообщение с наказанием",
            value=f"[Перейти]({self.message_link})",
            inline=False
        )

        embed.set_footer(text=f"user_id:{interaction.user.id}")

        channel = guild.get_channel(APPEAL_CHANNEL_ID)

        await channel.send(
            content=roles_ping,
            embed=embed,
            view=AppealManageView()
        )

        await interaction.response.send_message(
            "✅ Ваше обжалование отправлено",
            ephemeral=True
        )



class AppealView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    def get_punished_id(self, interaction):
        msg = interaction.message

        if msg.embeds:
            embed = msg.embeds[0]
            if embed.footer and embed.footer.text:
                try:
                    return int(embed.footer.text.split(":")[1])
                except:
                    pass

        if "user_id:" in msg.content:
            try:
                return int(msg.content.split("user_id:")[1])
            except:
                pass

        return None

    @discord.ui.button(
        label="Обжаловать наказание",
        style=discord.ButtonStyle.secondary,
        emoji="⚖️",
        custom_id="appeal_button"
    )
    async def appeal(self, interaction: discord.Interaction, button: discord.ui.Button):

        punished_member_id = self.get_punished_id(interaction)

        if not punished_member_id or interaction.user.id != punished_member_id:
            await interaction.response.send_message(
                "❌ Вы не можете обжаловать чужое наказание",
                ephemeral=True
            )
            return

        await interaction.response.send_modal(
            AppealModal(
                message_link=interaction.message.jump_url
            )
        )

    @discord.ui.button(
        label="Обжалование с док-вом",
        style=discord.ButtonStyle.primary,
        custom_id="appeal_with_proof"
    )
    async def appeal_with_proof(self, interaction: discord.Interaction, button: discord.ui.Button):

        punished_member_id = self.get_punished_id(interaction)

        if not punished_member_id or interaction.user.id != punished_member_id:
            await interaction.response.send_message(
                "❌ Вы не можете обжаловать чужое наказание",
                ephemeral=True
            )
            return

        await interaction.response.send_modal(
            AppealWithProofModal(
                punished_member_id=punished_member_id,
                message_link=interaction.message.jump_url
            )
        )



class AppealManageView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def interaction_check(self, interaction: discord.Interaction):
        if not has_owner_role(interaction.user):
            await interaction.response.send_message(
                "❌ Только Owner / Dep.Owner могут обрабатывать апелляции",
                ephemeral=True
            )
            return False
        return True

    # ================= APPROVE =================

    @discord.ui.button(
        label="Одобрить",
        style=discord.ButtonStyle.success,
        emoji="✅",
        custom_id="appeal_approve"
    )
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):

        msg = interaction.message
        embed = msg.embeds[0]

        embed.color = discord.Color.green()
        embed.add_field(
            name="Решение",
            value=f"✅ Обжалование одобрено {interaction.user.mention}",
            inline=False
        )

        user_id = get_user_id_from_embed(embed)

        if user_id:
            try:
                member = await interaction.guild.fetch_member(user_id)
                await member.send(
                    f"✅ Ваше обжалование ОДОБРЕНО!\n\n"
                    f"Модератор: {interaction.user.mention}"
                )
            except:
                pass

        for item in self.children:
            item.disabled = True

        await msg.edit(embed=embed, view=self)
        await interaction.response.send_message("✅ Обжалование одобрено", ephemeral=True)

    # ================= REJECT =================

    @discord.ui.button(
        label="Отклонить",
        style=discord.ButtonStyle.danger,
        emoji="❌",
        custom_id="appeal_reject"
    )
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(
            RejectReasonModal(interaction.message)
        )



class RejectReasonModal(discord.ui.Modal, title="Причина отклонения"):

    reason = discord.ui.TextInput(
        label="Почему отклонено?",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=500
    )

    def __init__(self, message: discord.Message):
        super().__init__()
        self.message = message

    async def on_submit(self, interaction: discord.Interaction):

        await interaction.response.defer(ephemeral=True)

        msg = self.message
        embed = msg.embeds[0]

        embed.color = discord.Color.red()
        embed.add_field(
            name="Решение",
            value=f"❌ Обжалование отклонено {interaction.user.mention}\nПричина: {self.reason.value}",
            inline=False
        )

        user_id = get_user_id_from_embed(embed)

        if user_id:
            try:
                member = await interaction.guild.fetch_member(user_id)
                await member.send(
                    f"❌ Ваше обжалование ОТКЛОНЕНО\n\n"
                    f"Причина:\n{self.reason.value}\n\n"
                    f"Модератор: {interaction.user.mention}"
                )
            except:
                pass

        view = discord.ui.View.from_message(msg)
        for item in view.children:
            item.disabled = True

        await msg.edit(embed=embed, view=view)
        await interaction.followup.send("❌ Обжалование отклонено", ephemeral=True)







# ================== APPROVE VIEW ==================

class ICRejectReasonModal(discord.ui.Modal, title="Причина отклонения IC-отпуска"):

    reason = discord.ui.TextInput(
        label="Причина отклонения",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=500
    )

    def __init__(self, message: discord.Message, user_id: int):
        super().__init__()
        self.message = message
        self.user_id = user_id

    async def on_submit(self, interaction: discord.Interaction):

        embed = self.message.embeds[0]
        embed.color = discord.Color.red()

        embed.description += (
            f"\n\n**Статус:** Отклонено"
            f"\n**Причина:** {self.reason.value}"
            f"\n**Отклонил:** {interaction.user.display_name}"
        )

        await self.message.edit(embed=embed)

        member = interaction.guild.get_member(self.user_id)

        if member:
            try:
                await member.send(
                    f"❌ Ваш IC-отпуск отклонён.\n"
                    f"Причина: {self.reason.value}"
                )
            except discord.Forbidden:
                pass

        await interaction.response.send_message(
            "❌ Заявка отклонена",
            ephemeral=True
        )




class ICApproveView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
    label="Одобрить",
    style=discord.ButtonStyle.success,
    custom_id="ic_approve"
    )
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):

        if not has_high_staff_role(interaction.user):
            await interaction.response.send_message(
                "❌ У вас нет прав",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        embed = interaction.message.embeds[0]
        footer = embed.footer.text

        if not footer:
            await interaction.followup.send("Данные заявки не найдены", ephemeral=True)
            return

        try:
            parts = dict(item.split(":") for item in footer.split(";"))
            user_id = int(parts["user_id"])
            duration_minutes = int(parts["duration"])
        except Exception:
            await interaction.followup.send(
                "Ошибка чтения данных заявки",
                ephemeral=True
            )
            return

        until = datetime.now(timezone.utc) + timedelta(minutes=duration_minutes)

        ic_vacations[str(user_id)] = {
            "until": until.isoformat(),
            "approved_by": interaction.user.id
        }

        save_ic(ic_vacations)

        embed.color = discord.Color.green()
        embed.description += (
            f"\n\n**Статус:** Одобрено"
            f"\n**Одобрил:** {interaction.user.display_name}"
            f"\n**До:** {until.astimezone(MSK).strftime('%d.%m.%Y %H:%M МСК')}"
        )

        for item in self.children:
            item.disabled = True

        await interaction.message.edit(embed=embed, view=self)

        user = interaction.client.get_user(user_id)
        if user:
            try:
                await user.send(
                    f"Ваш IC-отпуск одобрен до "
                    f"{until.astimezone(MSK).strftime('%H:%M МСК')}"
                )
            except:
                pass

        await interaction.followup.send("✅ Заявка одобрена", ephemeral=True)




    @discord.ui.button(
        label="Отклонить",
        style=discord.ButtonStyle.danger,
        custom_id="ic_reject"
    )
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):

        if not has_high_staff_role(interaction.user):
            await interaction.response.send_message(
                "❌ У вас нет прав",
                ephemeral=True
            )
            return

        embed = interaction.message.embeds[0]
        footer = embed.footer.text

        if not footer:
            await interaction.response.send_message(
                "Данные заявки не найдены",
                ephemeral=True
            )
            return

        try:
            parts = dict(item.split(":") for item in footer.split(";"))
            user_id = int(parts["user_id"])
        except Exception:
            await interaction.response.send_message(
                "Ошибка чтения данных заявки",
                ephemeral=True
            )
            return

        await interaction.response.send_modal(
            ICRejectReasonModal(
                message=interaction.message,
                user_id=user_id
            )
        )








# ================== PANEL VIEW ==================

class ICRequestView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Подать заявку",
        style=discord.ButtonStyle.primary,
        custom_id="ic_vacation_button"
    )
    async def open(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ICVacationModal())

# ================== ROLLBACK ==================

def save_rollback_data():
    with open(ROLLBACK_FILE, "w", encoding="utf-8") as f:
        json.dump(ROLLBACK_REQUESTS, f, ensure_ascii=False, indent=4)


def load_rollback_data():
    global ROLLBACK_REQUESTS

    if not ROLLBACK_FILE.exists():
        ROLLBACK_REQUESTS = {}
        with open(ROLLBACK_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f, ensure_ascii=False, indent=4)
        return

    if ROLLBACK_FILE.stat().st_size == 0:
        ROLLBACK_REQUESTS = {}
        return

    with open(ROLLBACK_FILE, "r", encoding="utf-8") as f:
        ROLLBACK_REQUESTS = json.load(f)


class RollbackEditView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="✏️ Изменить откат",
        style=discord.ButtonStyle.secondary,
        custom_id="ch_rollback"
    )
    async def edit(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = interaction.message.embeds[0] if interaction.message.embeds else None
        footer = embed.footer.text if (embed and embed.footer) else ""

        if not footer.startswith("request_key:"):
            await interaction.response.send_message("❌ Не найден ключ отката в сообщении", ephemeral=True)
            return

        request_key = footer.split("request_key:", 1)[1].strip()

        await interaction.response.send_modal(
            RollbackLinkModal(
                request_key=request_key,
                channel_id=interaction.channel.id,
                edit=True
            )
        )


class RollbackLinkModal(discord.ui.Modal, title="Откат"):
    link = discord.ui.TextInput(
        label="Ссылка на откат",
        placeholder="Ссылка",
        required=True
    )

    def __init__(self, request_key: str, channel_id: int, edit: bool = False):
        super().__init__()
        self.request_key = request_key
        self.channel_id = channel_id
        self.edit = edit

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        req = ROLLBACK_REQUESTS.get(self.request_key)
        if not req:
            await interaction.followup.send("❌ Запрос не найден", ephemeral=True)
            return

        data = req["players"].get(str(self.channel_id))
        if not data:
            await interaction.followup.send("❌ Данные игрока не найдены", ephemeral=True)
            return

        data["link"] = self.link.value
        save_rollback_data()

        try:
            channel = interaction.channel
            msg = await channel.fetch_message(data["message_id"])
        except discord.NotFound:
            await interaction.followup.send("❌ Сообщение с запросом не найдено", ephemeral=True)
            return

        if not msg.embeds:
            await interaction.followup.send("❌ Embed в сообщении не найден", ephemeral=True)
            return
        embed = msg.embeds[0]
        footer_text =  embed.footer.text if embed.footer else None
        embed.clear_fields()
        if footer_text:
            embed.set_footer(text=footer_text)

        creator_id = req.get("created_by")
        if creator_id:
            embed.add_field(
                name="Запрашивающий",
                value=f"<@{creator_id}>",
                inline=False
            )

        embed.add_field(
            name="Откат",
            value=self.link.value,
            inline=False
        )

        await msg.edit(embed=embed, view=RollbackEditView())

        await interaction.followup.send("✅ Откат сохранён", ephemeral=True)


def make_request_key(capt_id: int, requested_by: int, comment: str) -> str:
    base = comment.strip().lower()
    base = re.sub(r"\s+", " ", base)

    base = re.sub(r"[^a-zа-я0-9 ._\-]", "", base)

    base = base[:80].strip()
    return f"capt:{capt_id}:{requested_by}:{base}"

def member_name_candidates(member: discord.Member) -> list[str]:
    name = member.display_name
    if "|" in name:
        name = name.split("|", 1)[1].strip()

    parts = re.split(r"\s+", name.lower().strip())
    parts = [re.sub(r"[^a-zа-я]", "", p) for p in parts]
    return [p for p in parts if p]

def find_ticket_by_member(guild: discord.Guild, member: discord.Member):
    for token in member_name_candidates(member):
        ch = find_ticket_by_player(guild, token)
        if ch:
            return ch
    return None

async def send_rollback_requests_for_capt(guild, capt_id, comment, requested_by):
    data = CAPT_DATA.get(capt_id)
    if not data:
        return 0, 0

    request_key = make_request_key(capt_id, requested_by, comment)

    if request_key not in ROLLBACK_REQUESTS:
        ROLLBACK_REQUESTS[request_key] = {
            "capt_id": capt_id,
            "comment": comment,
            "players": {},
            "created_by": requested_by,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        save_rollback_data()

    sent = 0
    missed = 0

    main_snapshot = list(data["main"].items())

    for uid, _comment in main_snapshot:
        member = guild.get_member(uid)
        if not member:
            missed += 1
            continue

        ticket = find_ticket_by_member(guild, member)
        if not ticket:
            missed += 1
            continue

        embed = discord.Embed(
            title="Запрос отката",
            description=f"**Комментарий:**\n{comment}",
            color=discord.Color.orange()
        )
        embed.add_field(name="Запрашивающий", value=f"<@{requested_by}>", inline=False)
        embed.set_footer(text=f"request_key:{request_key}")

        msg = await ticket.send(content=member.mention, embed=embed, view=RollbackLinkView())

        ROLLBACK_REQUESTS[request_key]["players"][str(ticket.id)] = {
            "name": member.display_name,
            "ticket_id": ticket.id,
            "message_id": msg.id,
            "link": None
        }
        save_rollback_data()
        sent += 1

    return sent, missed

class RollbackLinkView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Прикрепить откат",
        style=discord.ButtonStyle.primary,
        custom_id="at_rollback"
    )
    async def attach(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = interaction.message.embeds[0] if interaction.message.embeds else None
        footer = embed.footer.text if (embed and embed.footer) else ""

        if not footer.startswith("request_key:"):
            await interaction.response.send_message("❌ Не найден ключ отката в сообщении", ephemeral=True)
            return

        request_key = footer.split("request_key:", 1)[1].strip()

        await interaction.response.send_modal(
            RollbackLinkModal(
                request_key=request_key,
                channel_id=interaction.channel.id
            )
        )




# ================== MOVE ==================

class ActivityControlView(discord.ui.View):
    def __init__(self, channel_id: int):
        super().__init__(timeout=None)
        self.channel_id = channel_id

    @discord.ui.button(label="🟢 Зашёл в войс", style=discord.ButtonStyle.success)
    async def move_to_voice(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not has_high_staff_role(interaction.user):
            await interaction.response.send_message(
                "❌ У вас нет прав для изменения отчёта актива",
                ephemeral=True
            )
            return

        data = LAST_ACTIVITY_REPORT.get(self.channel_id)
        if not data or not data["not_voice"]:
            await interaction.response.send_message(
                "❌ Нет игроков для переноса",
                ephemeral=True
            )
            return

        if len(data["not_voice"]) <= 25:
            await interaction.response.send_message(
                "Кто зашёл в войс?",
                view=MovePlayerSelect(self.channel_id, mode="voice"),
                ephemeral=True
            )
        else:
            await interaction.response.send_modal(
                MovePlayerModal(self.channel_id, mode="voice")
            )



    @discord.ui.button(label="✈️ Снять IC-отпуск", style=discord.ButtonStyle.primary)
    async def remove_ic(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not has_high_staff_role(interaction.user):
            await interaction.response.send_message(
                "❌ У вас нет прав для изменения отчёта актива",
                ephemeral=True
            )
            return

        data = LAST_ACTIVITY_REPORT.get(self.channel_id)
        if not data or not data["ic"]:
            await interaction.response.send_message(
                "❌ Нет игроков в IC-отпуске",
                ephemeral=True
            )
            return

        if len(data["ic"]) <= 25:
            await interaction.response.send_message(
                "Кто вышел из IC-отпуска?",
                view=MovePlayerSelect(self.channel_id, mode="ic"),
                ephemeral=True
            )
        else:
            await interaction.response.send_modal(
                MovePlayerModal(self.channel_id, mode="ic")
            )

    @discord.ui.button(
    label="🚨 Выдать штрафы",
    style=discord.ButtonStyle.danger
    )
    async def give_penalties(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        if not has_high_staff_role(interaction.user):
            await interaction.response.send_message(
                "❌ У вас нет прав для выдачи штрафов",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        data = LAST_ACTIVITY_REPORT.get(self.channel_id)
        if not data or not data["not_voice"]:
            await interaction.followup.send(
                "ℹ️ Нет игроков для штрафа",
                ephemeral=True
            )
            return

        guild = interaction.guild
        punish_channel = guild.get_channel(PUNISH_CHANNEL_ID)
        appeal_channel = guild.get_channel(APPEAL_CHANNEL_ID)

        if not punish_channel or not appeal_channel:
            await interaction.followup.send(
                "❌ Ошибка конфигурации каналов",
                ephemeral=True
            )
            return

        issued = 0

        for raw in list(data["not_voice"]):
            name = clean_player_name(raw)

            member = discord.utils.find(
                lambda m: names_match(m.display_name, name),
                guild.members
            )
            if not member:
                continue

            next_role, old_role = get_next_penalty_role(member)

            if not next_role:
                continue

            if old_role:
                await member.remove_roles(
                    old_role,
                    reason="Повышение уровня штрафа"
                )

            await member.add_roles(
                next_role,
                reason="В игре, но не в войсе"
            )

            text = (
                f"1. {member.mention}\n"
                f"2. **3.6.** Запрещено игнорировать регрупп на различные теги в ⁠╭・📢 news "
                f"без уведомления ⁠│・ ✅ ic-отпуск ⁠│・ Штраф\n"
                f"3. {interaction.channel.mention}\n"
                f"user_id:{member.id}"
            )

            await punish_channel.send(
                text,
                view=AppealView()
            )

            issued += 1

        embed = interaction.message.embeds[0]

        embed.add_field(
            name="🚨 Штрафы выданы",
            value=f"Кто выдал: {interaction.user.mention}\n"
                f"Количество: {issued}",
            inline=False
        )

        button.disabled = True
        await interaction.message.edit(embed=embed, view=self)


        await interaction.followup.send(
            f"🚨 Штрафы выданы: **{issued}**",
            ephemeral=True
        )

class MeetingControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)


class MeetingPunishView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="🟢 Пришёл на собрание",
        style=discord.ButtonStyle.success
    )
    async def mark_present(self, interaction: discord.Interaction, button):

        if not has_high_staff_role(interaction.user):
            await interaction.response.send_message(
                "❌ Нет прав",
                ephemeral=True
            )
            return

        await interaction.response.send_modal(MeetingPresentModal())

    @discord.ui.button(
        label="🔴 Выдать выговор",
        style=discord.ButtonStyle.danger,
        custom_id="meeting_reprimand"
    )
    async def reprimand(self, interaction: discord.Interaction, button):

        guild = interaction.guild
        reprimand_role = guild.get_role(REPRIMAND_ROLE_ID)
        punish_channel = guild.get_channel(PUNISH_CHANNEL_ID)
        activity_channel = guild.get_channel(ACTIVITY_REPORT_CHANNEL_ID)

        if not reprimand_role or not punish_channel or not activity_channel:
            await interaction.response.send_message(
                "❌ Ошибка конфигурации",
                ephemeral=True
            )
            return

        present, absent = get_meeting_attendance(guild)

        approved_ids = set(MEETING_ABSENCE_DATA["approved"].keys())

        absent = [
            m for m in absent
            if m.id not in approved_ids
            and m.id not in MEETING_ABSENCE_DATA.get("manual_present", set())
        ]

        if not absent:
            await interaction.response.send_message(
                "✅ Нет нарушителей",
                ephemeral=True
            )
            return

        issued = 0

        for member in absent:
            if reprimand_role in member.roles:
                continue

            try:
                await member.add_roles(
                    reprimand_role,
                    reason="Неявка на собрание семьи"
                )

                text = (
                    f"1. {member.mention}\n"
                    f"2. **2.7** Неявка на собрание без предупреждения. I Выговор [1/2]\n"
                    f"3. {activity_channel.mention}"
                )

                await punish_channel.send(
                    text,
                    view=AppealView(member.id)
                )

                issued += 1

            except:
                continue


        await interaction.response.send_message(
            f"🔴 Выговор выдан: **{issued}**",
            ephemeral=True
        )

        button.disabled = True
        await interaction.message.edit(view=self)

class MeetingPresentModal(discord.ui.Modal, title="Перенос в присутствующие"):

    user_id = discord.ui.TextInput(
        label="ID пользователя",
        placeholder="Введите ID участника",
        required=True,
        max_length=20
    )

    async def on_submit(self, interaction: discord.Interaction):

        if not has_high_staff_role(interaction.user):
            await interaction.response.send_message(
                "❌ Нет прав",
                ephemeral=True
            )
            return

        try:
            uid = int(self.user_id.value)
        except ValueError:
            await interaction.response.send_message(
                "❌ Неверный ID",
                ephemeral=True
            )
            return

        guild = interaction.guild
        member = guild.get_member(uid)

        if not member:
            await interaction.response.send_message(
                "❌ Пользователь не найден",
                ephemeral=True
            )
            return

        manual = MEETING_ABSENCE_DATA.setdefault("manual_present", set())
        manual.add(uid)

        report_id = MEETING_ABSENCE_DATA.get("report_message_id")

        if report_id:
            try:
                report_channel = guild.get_channel(ACTIVITY_REPORT_CHANNEL_ID)
                msg = await report_channel.fetch_message(report_id)

                new_embed = build_meeting_embed(guild)
                await msg.edit(embed=new_embed)

            except Exception as e:
                print("Ошибка обновления отчёта:", e)

        await interaction.response.send_message(
            "✅ Участник перенесён в присутствующие",
            ephemeral=True
        )

def safe_remove(lst: list, value) -> bool:
    try:
        lst.remove(value)
        return True
    except ValueError:
        return False

class MovePlayerSelect(discord.ui.View):
    def __init__(self, channel_id: int, mode: str):
        super().__init__(timeout=60)
        self.channel_id = channel_id
        self.mode = mode

        data = LAST_ACTIVITY_REPORT.get(channel_id)
        if not data:
            return

        source = data["not_voice"] if mode == "voice" else data["ic"]
        options = [
            discord.SelectOption(
                label=clean_player_name(name)[:100],
                value=name[:100]
            )
            for name in sorted(source)
        ]

        self.select = discord.ui.Select(
            placeholder="Выбери игрока",
            options=options,
            min_values=1,
            max_values=1
        )
        self.select.callback = self.on_select
        self.add_item(self.select)

    async def on_select(self, interaction: discord.Interaction):
        if not has_high_staff_role(interaction.user):
            await interaction.response.send_message("❌ У вас нет прав", ephemeral=True)
            return

        raw_name = self.select.values[0]
        data = LAST_ACTIVITY_REPORT.get(self.channel_id)
        if not data:
            await interaction.response.send_message("❌ Отчёт не найден", ephemeral=True)
            return

        clean = clean_player_name(raw_name)
        new_value = f"✅ {clean}"

        if self.mode == "voice":
            safe_remove(data["not_voice"], raw_name)
        else:
            safe_remove(data["ic"], raw_name)

        if new_value not in data["both"]:
            data["both"].append(new_value)

        channel = interaction.guild.get_channel(self.channel_id)
        msg = await channel.fetch_message(data["message_id"])

        embed = build_activity_embed(data)
        await msg.edit(embed=embed)

        await interaction.response.edit_message(
            content=f"✅ {clean} перемещён в «В игре и в войсе»",
            view=None
        )


class MovePlayerModal(discord.ui.Modal, title="Перенос игрока"):
    player_name = discord.ui.TextInput(
        label="Ник игрока",
        placeholder="Введите ник игрока",
        required=True,
        max_length=50
    )

    def __init__(self, channel_id: int, mode: str):
        super().__init__()
        self.channel_id = channel_id
        self.mode = mode

    async def on_submit(self, interaction: discord.Interaction):
        if not has_high_staff_role(interaction.user):
            await interaction.response.send_message("❌ У вас нет прав", ephemeral=True)
            return

        data = LAST_ACTIVITY_REPORT.get(self.channel_id)
        if not data:
            await interaction.response.send_message("❌ Отчёт не найден", ephemeral=True)
            return

        source_key = "not_voice" if self.mode == "voice" else "ic"
        source = data[source_key]

        entered = self.player_name.value.strip()
        found = None

        for name in source:
            if names_match(clean_player_name(name), entered):
                found = name
                break

        if not found:
            await interaction.response.send_message(f"❌ {entered} не найден в списке", ephemeral=True)
            return

        clean = clean_player_name(found)
        new_value = f"✅ {clean}"

        source.discard(found)
        data["both"].add(new_value)

        channel = interaction.guild.get_channel(self.channel_id)
        msg = await channel.fetch_message(data["message_id"])
        await msg.edit(embed=build_activity_embed(data))

        await interaction.response.send_message(f"✅ {clean} перенесён в «В игре и в войсе»", ephemeral=True)





# ================== BOT ==================

class Bot(discord.Client):
    def __init__(self, *, intents: discord.Intents):
        super().__init__(intents=intents)
        self.voice_initialized = False

    async def setup_hook(self):
        global VOICE_STATS, ROLLBACK_REQUESTS, daily_voice_time, voice_sessions, ic_vacations
        daily_voice_time, voice_sessions, last_reset_date = load_voice_stats()
        if not last_reset_date:
            last_reset_date = datetime.now(MSK).date().isoformat()
            save_voice_stats(daily_voice_time, voice_sessions, last_reset_date)
        self.last_voice_reset_date = last_reset_date
        load_rollback_data()
        self.loop.create_task(self.daily_voice_top_task())
        VOICE_STATS = load_json(VOICE_STATS_FILE, {})
        ic_vacations = load_ic()
        load_birthdays()
        self.add_view(BirthdayPanelView())
        self.loop.create_task(birthday_daily_task(self))
        self.add_view(RollbackLinkView())
        self.add_view(RollbackEditView())
        self.add_view(ICRequestView())
        self.add_view(FamilyRequestView())
        self.add_view(MeetingAbsencePanelView())
        self.add_view(MeetingAbsenceApproveView())
        self.add_view(AppealManageView())
        self.add_view(AppealView())
        self.add_view(ICApproveView())
        self.add_view(DisciplinePanelView())
        self.add_view(CaptPanelView())
        print("VOICE loaded:", len(daily_voice_time), len(voice_sessions))
        print("VOICE last_reset_date:", self.last_voice_reset_date)
        print("IC loaded:", len(ic_vacations), "file:", IC_FILE)

    async def daily_voice_top_task(self):
        await self.wait_until_ready()
        while not self.is_closed():
            now = datetime.now(MSK)
            target = now.replace(hour=23, minute=59, second=0, microsecond=0)
            if now >= target:
                target += timedelta(days=1)

            sleep_seconds = (target - now).total_seconds()
            await asyncio.sleep(sleep_seconds)

            today_str = datetime.now(MSK).date().isoformat()

            if self.last_voice_reset_date == today_str:
                await asyncio.sleep(60)
                continue

            for guild in self.guilds:
                channel = guild.get_channel(VOICE_TOP_CHANNEL_ID)
                if not channel:
                    continue
                embed = build_voice_top_embed(guild)
                await channel.send(embed=embed)

            daily_voice_time.clear()

            now_utc = datetime.now(timezone.utc)
            for session in voice_sessions.values():
                session["joined_at"] = now_utc.isoformat()

            self.last_voice_reset_date = today_str
            save_voice_stats(daily_voice_time, voice_sessions, self.last_voice_reset_date)



    async def ic_cleanup(self):
        await self.wait_until_ready()
        while not self.is_closed():
            now = datetime.now(timezone.utc)
            expired = [u for u, d in ic_vacations.items() if d["until"] <= now]
            for u in expired:
                del ic_vacations[u]
            await asyncio.sleep(60)

    async def on_ready(self):
        for guild in bot.guilds:
            await ensure_birthday_panel(self, guild)
            await ensure_birthdays_list_message(self, guild)
        print("Birthday system ready")
        self.add_view(FamilyApproveView())
        self.add_view(FamilyInWorkView())
        self.add_view(FamilyFinalView())
        print("✅ Persistent Family Views зарегистрированы")
        print(f"✅ Бот запущен: {self.user}")
        await ensure_capt_panel(self)

        discipline_channel = self.get_channel(DISCIPLINE_CHANNEL_ID)

        embed = discord.Embed(
            title="Панель дисциплины",
            description="Используйте кнопки ниже для управления отчётами.",
            color=discord.Color.blue()
        )
        embed.set_image(url="https://media.discordapp.net/attachments/675341437336027166/1014634234444521583/alliance2.gif?ex=697f1004&is=697dbe84&hm=a6d557da5d812193e658e2ce2624dcc77ed4c3569202d73e7e8d912d4be4f95c&")


        panel_exists = False

        async for msg in discipline_channel.history(limit=10):
            if msg.author == self.user and msg.components:
                panel_exists = True
                break

        if not panel_exists:
            await discipline_channel.send(
                embed=embed,
                view=DisciplinePanelView()
            )



        ic_channel = self.get_channel(IC_REQUEST_CHANNEL_ID)
        if not ic_channel:
            return

        ic_panel_exists = False
        async for msg in ic_channel.history(limit=10):
            if msg.author == self.user and msg.components:
                ic_panel_exists = True
                break

        if not ic_panel_exists:
            embed = discord.Embed(
                title="IC-отпуск",
                color=discord.Color.blue()
            )
            embed.set_image(url="https://media.discordapp.net/attachments/675341437336027166/1014634234444521583/alliance2.gif?ex=697f1004&is=697dbe84&hm=a6d557da5d812193e658e2ce2624dcc77ed4c3569202d73e7e8d912d4be4f95c&")

            msg = await ic_channel.send(embed=embed, view=ICRequestView())
            await msg.pin()

        family_channel = self.get_channel(FAMILY_REQUEST_CHANNEL_ID)
        if not family_channel:
            return

        family_panel_exists = False
        async for msg in family_channel.history(limit=10):
            if msg.author == self.user and msg.components:
                family_panel_exists = True
                break

        if not family_panel_exists:

            embed = discord.Embed(
                title="Путь в семью начинается здесь!",
                description="Обычно заявки обрабатываются в течение 24 часов — всё зависит от того, насколько загружены наши рекрутеры на данный момент.",
                color=discord.Color.blue()
            )
            embed.set_image(url="https://media.discordapp.net/attachments/675341437336027166/1014634234444521583/alliance2.gif?ex=697f1004&is=697dbe84&hm=a6d557da5d812193e658e2ce2624dcc77ed4c3569202d73e7e8d912d4be4f95c&")
            embed.set_footer(text="AllianceBot")

            msg = await family_channel.send(embed=embed, view=FamilyRequestView())
            await msg.pin()

        # ================= meeting panel =================

        meeting_channel = self.get_channel(MEETING_PANEL_CHANNEL)

        if meeting_channel:

            meeting_panel_exists = False

            async for msg in meeting_channel.history(limit=10):
                if msg.author == self.user and msg.components:
                    meeting_panel_exists = True
                    break

            if not meeting_panel_exists:
                msg = await meeting_channel.send(
                    embed=build_meeting_absence_panel_embed(),
                    view=MeetingAbsencePanelView()
                )
                await msg.pin()

                MEETING_ABSENCE_DATA["panel_message_id"] = msg.id


    # ================= VOICE SYNC =================

        if not self.voice_initialized:
            print("🔊 Синхронизация голосовых каналов...")

            now = datetime.now(timezone.utc)

            for guild in self.guilds:
                for channel in guild.voice_channels:
                    if guild.afk_channel and channel.id == guild.afk_channel.id:
                        continue
                    for member in channel.members:
                        if member.bot:
                            continue

                        if member.voice and not member.voice.self_deaf and not member.voice.deaf:
                            uid = str(member.id)

                            if uid not in voice_sessions:
                                voice_sessions[uid] = {
                                    "channel_id": channel.id,
                                    "joined_at": now.isoformat()
                                }
                            else:
                                voice_sessions[uid]["channel_id"] = channel.id

            save_voice_stats(daily_voice_time, voice_sessions, self.last_voice_reset_date)
            self.voice_initialized = True

    async def on_voice_state_update(self, member, before, after):
        if member.bot:
            return

        now = datetime.now(timezone.utc)
        user_id = str(member.id)

        def stop_session():
            session = voice_sessions.pop(user_id, None)
            if not session:
                return
            joined_at = datetime.fromisoformat(session["joined_at"])
            delta = (now - joined_at).total_seconds()
            daily_voice_time[member.id] = daily_voice_time.get(member.id, 0) + int(delta)
            save_voice_stats(daily_voice_time, voice_sessions, self.last_voice_reset_date)

        if user_id in voice_sessions:
            if (
                after.channel is None
                or after.self_deaf
                or after.deaf
                or (member.guild.afk_channel and after.channel.id == member.guild.afk_channel.id)
            ):
                stop_session()
                return

            if after.channel and voice_sessions[user_id].get("channel_id") != after.channel.id:
                voice_sessions[user_id]["channel_id"] = after.channel.id
                save_voice_stats(daily_voice_time, voice_sessions, self.last_voice_reset_date)

        if (
            after.channel
            and not after.self_deaf
            and not after.deaf
            and (not member.guild.afk_channel or after.channel.id != member.guild.afk_channel.id)
        ):
            if user_id not in voice_sessions:
                voice_sessions[user_id] = {
                    "channel_id": after.channel.id,
                    "joined_at": now.isoformat()
                }
                save_voice_stats(daily_voice_time, voice_sessions, self.last_voice_reset_date)

    
    async def on_message(self, message: discord.Message):
        if await handle_activity_fix_command(message):
            return

        if message.author.bot:
            return
        if await handle_capt_move_by_text(message):
            return
        user_id = message.author.id
        content = message.content.strip()
        now = datetime.now(timezone.utc)

        # ==================================================
        # APEAL WITH PROOF
        # ==================================================
        if user_id in WAITING_FOR_APPEAL_PROOF:

            data = WAITING_FOR_APPEAL_PROOF.pop(user_id)

            if not message.attachments:
                await message.reply(
                    "❌ Нужно отправить **хотя бы один скриншот**.",
                    delete_after=10
                )
                return

            guild = message.guild
            channel = guild.get_channel(APPEAL_CHANNEL_ID)

            owner_roles = [
                guild.get_role(rid)
                for rid in OWNER_ROLE_IDS
                if guild.get_role(rid)
            ]
            roles_ping = " ".join(r.mention for r in owner_roles)

            embed = discord.Embed(
                title="⚖️ Обжалование наказания (с доказательствами)",
                color=discord.Color.orange(),
                timestamp=datetime.now(timezone.utc)
            )

            embed.add_field(
                name="Игрок",
                value=f"{message.author.mention}",
                inline=False
            )

            embed.add_field(
                name="Оправдание",
                value=data["justification"],
                inline=False
            )

            embed.add_field(
                name="Сообщение с наказанием",
                value=f"[Перейти]({data['message_link']})",
                inline=False
            )

            embed.set_footer(text=f"user_id:{message.author.id}")

            files = [
                await att.to_file()
                for att in message.attachments
                if att.content_type and att.content_type.startswith("image/")
            ]

            await channel.send(
                content=roles_ping,
                embed=embed,
                files=files,
                view=AppealManageView()
            )

            try:
                await message.delete()
            except:
                pass

            return

        # ==================================================
        # FAMILY WAR — CAPT SCREENSHOT
        # ==================================================
        if user_id in WAITING_FOR_CAPT_SCREENSHOT:

            data = WAITING_FOR_CAPT_SCREENSHOT.pop(user_id)

            if not message.attachments:
                await message.reply(
                    "❌ Нужно отправить **скриншот квадрата**.",
                    delete_after=10
                )
                return

            attachment = message.attachments[0]
            file = await attachment.to_file()


            capt_id = int(time.time())

            CAPT_DATA[capt_id] = {
                "time": data["time"],
                "group_code": data["group_code"],
                "file": file,
                "applied": {},
                "main": {},
                "reserve": {},
                "closed": False,
            }

            try:
                await message.delete()
            except:
                pass

            await send_capt_war_embed(message.guild, capt_id)
            await send_capt_list_embed(message.guild, capt_id)

            return


        # ==================================================
        # VOICE TOP COMMAND
        # ==================================================
        if content.lower() == "!sobranie":

            if not has_high_staff_role(message.author):
                await message.channel.send("❌ Нет прав")
                return

            embed = build_meeting_embed(message.guild)
            await message.channel.send(embed=embed, view=MeetingControlView())
            return

        # ==================================================
        # ROLLBACK SYSTEM
        # ==================================================
        if user_id in WAITING_FOR_ROLLBACK:

            comment = WAITING_FOR_ROLLBACK.pop(user_id)
            message.content = comment
            content = comment

        if content.lower().strip().startswith("откат") and has_high_staff_role(message.author):

            req = ROLLBACK_REQUESTS.get(content)

            if not req:
                needle = content.strip().lower()
                for _key, _req in ROLLBACK_REQUESTS.items():
                    c = (_req.get("comment") or "").strip().lower()
                    if c == needle:
                        req = _req
                        break

            if not req:
                await message.channel.send("❌ Запрос откатов не найден по этому комментарию.")
                return

            lines = []
            for i, p in enumerate(req.get("players", {}).values(), start=1):
                status = "✅" if p.get("link") else "❌"
                lines.append(f"{i}. {status} {p.get('name','—')} — <#{p.get('ticket_id')}>")

            embed = discord.Embed(
                title="Отчёт по откатам",
                description=f"**Комментарий:**\n{req.get('comment', content)}\n\n" + "\n".join(lines),
                color=discord.Color.orange(),
                timestamp=now
            )

            await message.channel.send(embed=embed)
            return

            if not message.attachments:
                return

            all_game_names = set()

            for attachment in message.attachments:
                if attachment.content_type and attachment.content_type.startswith("image/"):
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
                        await attachment.save(tmp.name)
                        names = await asyncio.to_thread(extract_game_names, tmp.name)
                        all_game_names |= names

            if not all_game_names:
                return

            try:
                await message.delete()
            except:
                pass

            ROLLBACK_REQUESTS[content] = {
                "players": {},
                "created_by": message.author.id,
                "created_at": datetime.now().isoformat()
            }
            save_rollback_data()

            for name in all_game_names:
                ticket = find_ticket_by_player(message.guild, name)
                if not ticket:
                    continue

                embed = discord.Embed(
                    title="Запрос отката",
                    description=f"**Комментарий:**\n{content}",
                    color=discord.Color.orange()
                )
                creator_id = ROLLBACK_REQUESTS[content]["created_by"]
                embed.add_field(
                    name="Запрашивающий",
                    value=f"<@{creator_id}>",
                    inline=False
                )
                embed.set_footer(text=f"request_key:{content[:900]}")
                msg = await ticket.send(content="@here", embed=embed, view=RollbackLinkView())

                ROLLBACK_REQUESTS[content]["players"][str(ticket.id)] = {
                    "name": name,
                    "ticket_id": ticket.id,
                    "message_id": msg.id,
                    "link": None
                }

                save_rollback_data()

            return

        # ==================================================
        # ACTIVITY REQUEST
        # ==================================================
        if user_id in WAITING_FOR_ACTIVITY:

            if not message.attachments:
                return

            data = WAITING_FOR_ACTIVITY.pop(user_id)
            message.content = data["comment"]
            content = data["comment"]

        if message.channel.id != DISCIPLINE_CHANNEL_ID:
            return

        if not message.attachments:
            return

        comment = content or "—"
        all_game_names = set()

        for attachment in message.attachments:
            if attachment.content_type and attachment.content_type.startswith("image/"):
                with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
                    await attachment.save(tmp.name)
                    all_game_names |= extract_game_names(tmp.name)
        game_names = dedup_game_names(all_game_names)

        if not game_names:
            return

        try:
            await message.delete()
        except:
            pass

        largest_voice, required_left = get_largest_voice_channel_multi(self, message.guild)

        if largest_voice:
            voice_names = get_voice_names_from_channel(largest_voice, required_left)
            voice_keys = {game_to_key(v) for v in voice_names}
            voice_count = len([m for m in largest_voice.members if not m.bot])
            voice_channel_name = f"{largest_voice.guild.name} / {largest_voice.name}"
        else:
            voice_keys = set()
            voice_count = 0
            voice_channel_name = "—"

        active_ic = {}
        now = datetime.now(timezone.utc)

        for uid, d in ic_vacations.items():
            try:
                until = datetime.fromisoformat(d["until"])
                if until > now:
                    active_ic[int(uid)] = d
            except:
                continue

        both, not_voice, ic_players = [], [], []

        for g in game_names:
            g_fixed = fix_ocr_prefix(g)
            g_key = game_to_key(g_fixed)

            ic_hit = False
            for uid, d in active_ic.items():
                member = message.guild.get_member(uid)
                if member and names_match(member.display_name, g_fixed):
                    until_dt = d["until"]
                    if isinstance(until_dt, str):
                        until_dt = datetime.fromisoformat(until_dt)

                    ic_players.append(
                        f"✈️ {g_fixed} (до {until_dt.astimezone(MSK).strftime('%H:%M')})"
                    )
                    ic_hit = True
                    break

            if ic_hit:
                continue

            if g_key in voice_keys:
                both.append(g_fixed)
            else:
                not_voice.append(g_fixed)


        embed = build_activity_embed({
            "comment": comment,
            "players_total": len(game_names),
            "voice_count": voice_count,
            "voice_channel": voice_channel_name,
            "both": both,
            "not_voice": not_voice,
            "ic": ic_players,
            "created_at": now,
            "requested_by": message.author.id
        })

        report_channel = message.guild.get_channel(ACTIVITY_REPORT_CHANNEL_ID)

        msg = await report_channel.send(
            embed=embed,
            view=ActivityControlView(report_channel.id)
        )
        await interaction.response.send_message(
            f"✅ Отчёт отправлен!\n🔗 Перейти к отчёту: {msg.jump_url}",
            ephemeral=True
        )
        


        LAST_ACTIVITY_REPORT[report_channel.id] = {
            "message_id": msg.id,
            "both": list(both),
            "not_voice": list(not_voice),
            "ic": list(ic_players),
            "players_total": len(game_names),
            "voice_count": voice_count,
            "voice_channel": voice_channel_name,
            "comment": comment,
            "created_at": now,
            "requested_by": message.author.id
        }

        ACTIVITY_REPORTS[msg.id] = LAST_ACTIVITY_REPORT[report_channel.id]







    async def on_member_join(self, member: discord.Member):
        cfg = GUILD_CONFIG.get(member.guild.id)
        if not cfg:
            return

        log_channel_id = cfg.get("LOG_CHANNEL_ID")
        if not log_channel_id:
            return

        channel = self.get_channel(log_channel_id)
        if not channel:
            return

        now = datetime.now(MSK)

        embed = discord.Embed(
            title="Участник вошёл на сервер",
            color=discord.Color.green(),
            timestamp=now
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="ID пользователя", value=str(member.id), inline=False)
        embed.add_field(name="Никнейм", value=member.display_name, inline=True)
        embed.add_field(
            name="Время входа",
            value=now.strftime("%d.%m.%Y %H:%M:%S"),
            inline=True
        )

        await channel.send(
            content=f"{member.mention} вошёл на сервер",
            embed=embed
        )

    async def on_member_remove(self, member: discord.Member):
        cfg = GUILD_CONFIG.get(member.guild.id)
        if not cfg:
            return

        log_channel_id = cfg.get("LOG_CHANNEL_ID")
        if not log_channel_id:
            return

        channel = self.get_channel(log_channel_id)
        if not channel:
            return

        now = datetime.now(MSK)

        kick_entry = None

        async for entry in member.guild.audit_logs(
            limit=5,
            action=discord.AuditLogAction.kick
        ):
            if entry.target and entry.target.id == member.id:

                if (now - entry.created_at).total_seconds() < 10:
                    kick_entry = entry
                break

        # ================== EMBED ==================

        if kick_entry:

            embed = discord.Embed(
                title="Участник кикнут с сервера",
                color=discord.Color.orange(),
                timestamp=now
            )


            embed.add_field(
                name="Кикнул",
                value=kick_entry.user.mention if kick_entry.user else "—",
                inline=False
            )
            

            embed.add_field(
                name="Причина кика",
                value=kick_entry.reason or "Не указана",
                inline=False
            )

        else:

            embed = discord.Embed(
                title="Участник покинул сервер",
                color=discord.Color.red(),
                timestamp=now
            )


        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="ID пользователя", value=str(member.id), inline=False)
        embed.add_field(name="Никнейм", value=member.display_name, inline=True)
        embed.add_field(
            name="Время выхода",
            value=now.strftime("%d.%m.%Y %H:%M:%S"),
            inline=True
        )

        if kick_entry:
            text = f"{member.mention} кикнут с сервера"
        else:
            text = f"{member.mention} покинул сервер"

        await channel.send(
            content=text,
            embed=embed
        )


def update_main_field(embed: discord.Embed, value: str):
    """Обновляет или создаёт одно поле для статуса заявки"""
    if embed.fields:
        embed.set_field_at(0, name="⚡ Статус заявки", value=value, inline=False)
    else:
        embed.add_field(name="⚡ Статус заявки", value=value, inline=False)


class FamilyApproveView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    def get_user_id(self, embed: discord.Embed):
        return int(embed.footer.text.split(":")[1])

    @discord.ui.button(
        label="🔵 Допустить",
        style=discord.ButtonStyle.primary,
        custom_id="family_allow"
    )
    async def approve(self, interaction: discord.Interaction, button):

        await interaction.response.defer(ephemeral=True)

        embed = interaction.message.embeds[0]
        uid = self.get_user_id(embed)

        embed.color = discord.Color.blue()
        update_main_field(embed, f"✅ Допущено {interaction.user.mention}")

        await interaction.message.edit(
            embed=embed,
            view=FamilyInWorkView()
        )

        user = interaction.client.get_user(uid)
        if user:
            try:
                await user.send("✅ Ваша заявка допущена к рассмотрению, ожидайте ответа в течении 12ч.")
            except discord.Forbidden:
                pass

        await interaction.followup.send("Заявка допущена", ephemeral=True)

    @discord.ui.button(
        label="🟡 Отказать",
        style=discord.ButtonStyle.secondary,
        custom_id="family_initial_reject"
    )
    async def reject(self, interaction: discord.Interaction, button):

        embed = interaction.message.embeds[0]
        uid = self.get_user_id(embed)

        await interaction.response.send_modal(
            FamilyRejectReasonModal(
                channel_id=interaction.channel.id,
                message_id=interaction.message.id,
                user_id=uid
            )
        )



class FamilyRejectReasonModal(discord.ui.Modal, title="Причина отказа"):
    reason = discord.ui.TextInput(
        label="Причина отказа",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=500
    )

    def __init__(self, channel_id: int, message_id: int, user_id: int):
        super().__init__()
        self.channel_id = channel_id
        self.message_id = message_id
        self.user_id = user_id

    async def on_submit(self, interaction: discord.Interaction):

        await interaction.response.defer(ephemeral=True)

        channel = interaction.client.get_channel(self.channel_id)
        if not channel:
            return await interaction.followup.send(
                "Канал не найден",
                ephemeral=True
            )

        try:
            message = await channel.fetch_message(self.message_id)
        except discord.NotFound:
            await interaction.followup.send(
                "❌ Сообщение не найдено",
                ephemeral=True
            )
        if not message.embeds:
            return await interaction.followup.send(
                "Embed не найден",
                ephemeral=True
            )

        embed = message.embeds[0]
        embed.color = discord.Color.red()

        update_main_field(
            embed,
            f"❌ Отказано {interaction.user.mention}\n"
            f"**Причина:** {self.reason.value}"
        )

        await message.edit(embed=embed, view=None)

        user = interaction.client.get_user(self.user_id)
        if user:
            try:
                await user.send(
                    f"❌ Ваша заявка отклонена.\n"
                    f"Причина: {self.reason.value}"
                )
            except discord.Forbidden:
                pass

        await interaction.followup.send(
            "Заявка отклонена",
            ephemeral=True
        )


class FamilyInWorkView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    def get_user_id(self, embed: discord.Embed):
        return int(embed.footer.text.split(":")[1])

    @discord.ui.button(
        label="🕓 В работе",
        style=discord.ButtonStyle.secondary,
        custom_id="family_in_work"
    )
    async def in_work(self, interaction: discord.Interaction, button):

        await interaction.response.defer(ephemeral=True)

        embed = interaction.message.embeds[0]
        uid = self.get_user_id(embed)

        update_main_field(embed, f"🕓 В работе у {interaction.user.mention}")

        await interaction.message.edit(
            embed=embed,
            view=FamilyFinalView()
        )

        user = interaction.client.get_user(uid)
        if user:
            try:
                await user.send(
                    f"🕓 Вашу заявку взял в работу {interaction.user.mention}"
                )
            except discord.Forbidden:
                pass

        await interaction.followup.send("Заявка взята в работу", ephemeral=True)


class FamilyFinalView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    def get_user_id(self, embed: discord.Embed):
        return int(embed.footer.text.split(":")[1])

    @discord.ui.button(
        label="✅ Принять",
        style=discord.ButtonStyle.success,
        custom_id="family_accept"
    )
    async def accept(self, interaction: discord.Interaction, button):

        await interaction.response.defer(ephemeral=True)

        embed = interaction.message.embeds[0]
        uid = self.get_user_id(embed)

        embed.color = discord.Color.green()
        update_main_field(embed, f"🏆 Принят в семью ({interaction.user.mention})")

        await interaction.message.edit(embed=embed, view=None)

        user = interaction.client.get_user(uid)
        if user:
            try:
                await user.send("🎉 Ваша заявка в семью принята!")
            except discord.Forbidden:
                pass

        await interaction.followup.send("Игрок принят", ephemeral=True)

    @discord.ui.button(
        label="❌ Отказать",
        style=discord.ButtonStyle.danger,
        custom_id="family_final_reject"
    )
    async def deny(self, interaction: discord.Interaction, button):

        embed = interaction.message.embeds[0]
        uid = self.get_user_id(embed)

        await interaction.response.send_modal(
            FamilyFinalRejectModal(
                channel_id=interaction.channel.id,
                message_id=interaction.message.id,
                user_id=uid
            )
        )


class FamilyFinalRejectModal(discord.ui.Modal, title="Причина отказа"):

    reason = discord.ui.TextInput(
        label="Причина отказа",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=500
    )

    def __init__(self, channel_id: int, message_id: int, user_id: int):
        super().__init__()
        self.channel_id = channel_id
        self.message_id = message_id
        self.user_id = user_id

    async def on_submit(self, interaction: discord.Interaction):

        await interaction.response.defer(ephemeral=True)

        channel = interaction.client.get_channel(self.channel_id)
        message = await channel.fetch_message(self.message_id)

        embed = message.embeds[0]
        embed.color = discord.Color.red()

        update_main_field(
            embed,
            f"❌ Отказано {interaction.user.mention}\n"
            f"**Причина:** {self.reason.value}"
        )

        await message.edit(embed=embed, view=None)

        user = interaction.client.get_user(self.user_id)
        if user:
            try:
                await user.send(
                    f"❌ Ваша заявка в семью отклонена.\n"
                    f"Причина: {self.reason.value}"
                )
            except discord.Forbidden:
                pass

        await interaction.followup.send("Заявка отклонена", ephemeral=True)





class FamilyRequestModal(discord.ui.Modal, title="Заявка в семью"):

    name = discord.ui.TextInput(
        label="Ник / Статик / Имя / Возраст",
        placeholder="Nick | Static | Имя | Возраст",
        required=True
    )

    online = discord.ui.TextInput(
        label="Средний онлайн / Прайм-тайм",
        placeholder="Например: 4-6ч / 18:00–22:00",
        required=True
    )

    families = discord.ui.TextInput(
        label="В каких семьях были?",
        placeholder="Перечислите предыдущие семьи",
        required=False
    )

    source = discord.ui.TextInput(
        label="Как узнали о семье?",
        placeholder="Друзья / Discord / Игра",
        required=True
    )

    skills = discord.ui.TextInput(
        label="Откат с арены / капт (Сайга + Тяжка)",
        placeholder="Арена — ? | Капт — ?",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        channel = interaction.guild.get_channel(FAMILY_REQUESTS_CHANNEL_ID)
        curator_role = interaction.guild.get_role(CURATOR_ROLE_ID)

        content_text = f"{interaction.user.mention} отправил(а) заявку!"
        if curator_role:
            content_text += f" {curator_role.mention}"

        embed = discord.Embed(
            title="Новая заявка в семью",
            color=discord.Color.gold(),
            timestamp=datetime.now(timezone.utc)
        )

        embed.set_thumbnail(url=interaction.user.display_avatar.url)

        embed.add_field(name="Статус", value="⏳ На рассмотрении", inline=False)
        embed.add_field(name="**Данные:**", value=self.name.value, inline=False)
        embed.add_field(name="**Средний онлайн:**", value=self.online.value, inline=False)
        embed.add_field(name="**Предыдущие семьи:**", value=self.families.value or "—", inline=False)
        embed.add_field(name="**Откуда узнал:**", value=self.source.value, inline=False)
        embed.add_field(name="**Откаты:**", value=self.skills.value, inline=False)

        embed.set_footer(text=f"applicant:{interaction.user.id}")

        await channel.send(
            content=content_text,
            embed=embed,
            view=FamilyApproveView()
        )

        await interaction.followup.send(
            "✅ Ваша заявка отправлена и будет рассмотрена в течении 24ч.",
            ephemeral=True
        )



class FamilyRequestView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Подать заявку",
        style=discord.ButtonStyle.primary,
        custom_id="family_request_open"
    )
    async def open(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(FamilyRequestModal())


# ================== RUN ==================

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.voice_states = True

bot = Bot(intents=intents)
bot.run(TOKEN)
