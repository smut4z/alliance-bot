import os
import re
import cv2
import pytesseract
import tempfile
import discord
import time
import asyncio
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone

MSK = timezone(timedelta(hours=3))

GUILD_CONFIG = {
    652465386603675649: {  # сервер №1 
        "LOG_CHANNEL_ID": 975808442172325898,
    },
    1282692203839225977: {  # сервер №2
        "LOG_CHANNEL_ID": 1282692205257162839,
    }
}


# ================== ENV ==================

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")

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
FAMILY_ROLE_ID = int(os.getenv("FAMILY_ROLE_ID"))
TIER_ROLES = {
    "tier1": 1425248070286839909,
    "tier2": 1425249207702392924,
    "tier3": 1425249369564909679,
    "owner": 652466330905346051,
    "dep_owner": 868260293938130975,
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

ticket_counter = 0

def ticket_name_from_user(member: discord.Member) -> str:
    name = member.display_name.lower()

    if "|" in name:
        name = name.split("|", 1)[1]

    name = name.replace("_", "-")

    name = re.sub(r"[^a-z0-9а-я-]", "", name)

    return f"заявка-{name}"

def get_user_tier(member: discord.Member):
    for tier, role_id in TIER_ROLES.items():
        if any(r.id == role_id for r in member.roles):
            return tier
    return None


def get_meeting_attendance(guild: discord.Guild):

    channel = guild.get_channel(MEETING_VOICE_ID)

    if not channel:
        return set(), set()

    present = set()

    for member in channel.members:
        if member.bot:
            continue
        if member.voice.self_deaf or member.voice.deaf:
            continue

        present.add(member)

    family_role = guild.get_role(FAMILY_ROLE_ID)
    reprimand_role = guild.get_role(REPRIMAND_ROLE_ID)

    if not family_role:
        return present, set()

    family_members = {
        m for m in guild.members
        if not m.bot and (
            family_role in m.roles or
            (reprimand_role and reprimand_role in m.roles)
        )
    }

    absent = family_members - present
    return present, absent



def chunk_list(items, limit=1024):
    chunks = []
    current = ""

    for item in items:
        line = item + "\n"

        if len(current) + len(line) > limit:
            chunks.append(current)
            current = line
        else:
            current += line

    if current:
        chunks.append(current)

    return chunks



def build_meeting_embed(guild):
    present, absent = get_meeting_attendance(guild)

    approved = MEETING_ABSENCE_DATA["approved"]
    approved_ids = set(approved.keys())

    absent = [m for m in absent if m.id not in approved_ids]

    embed = discord.Embed(
        title="📊 Отчёт собрания",
        color=discord.Color.blue()
    )

    present_list = [m.mention for m in present]
    embed.add_field(
        name=f"✅ Присутствовали ({len(present_list)})",
        value="\n".join(present_list) if present_list else "—",
        inline=False
    )

    absent_list = [m.mention for m in absent]
    embed.add_field(
        name=f"❌ Отсутствовали ({len(absent_list)})",
        value="\n".join(absent_list) if absent_list else "—",
        inline=False
    )

    approved_list = []

    for uid, reason in approved.items():
        member = guild.get_member(uid)
        if member:
            approved_list.append(f"{member.mention} — {reason}")

    embed.add_field(
        name=f"🚫 Отсутствовали с причиной ({len(approved_list)})",
        value="\n".join(approved_list) if approved_list else "—",
        inline=False
    )

    return embed







#def has_discipline_role(member: discord.Member) -> bool:
 #   return any(role.id == DISCIPLINE_ROLE_ID for role in member.roles)

def has_high_staff_role(member: discord.Member) -> bool:
    return any(role.id in HIGH_STAFF_ROLE_IDS for role in member.roles)

def has_owner_role(member: discord.Member) -> bool:
    return any(role.id in OWNER_ROLE_IDS for role in member.roles)


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
    for field in embed.fields:
        if "ID:" in field.value:
            try:
                return int(field.value.split("ID:")[1].strip())
            except:
                return None
    return None


# ================== ACTIVITY REPORT STATE ==================

LAST_ACTIVITY_REPORT = {}
WAITING_FOR_ACTIVITY = {}
WAITING_FOR_ROLLBACK = {}
WAITING_FOR_ANALYZE = set()
WAITING_FOR_APPEAL_PROOF = {}


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

MEETING_ABSENCE_DATA = {
    "approved": {},   # uid -> reason
}

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

def normalize_name_full(name: str) -> str:
    name = name.lower().replace("_", " ")
    name = re.sub(r"[^a-z ]", "", name)
    name = re.sub(r"\s+", " ", name).strip()
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

def names_match(a: str, b: str) -> bool:
    a = normalize_name(a)
    b = normalize_name(b)
    if not a or not b:
        return False
    return a == b or a.startswith(b) or b.startswith(a)

def normalize_character_name(text: str) -> str:
    text = text.lower().strip()

    # если есть | — берём правую часть
    if "|" in text:
        text = text.split("|", 1)[1]

    # берём ТОЛЬКО первое слово (имя персонажа)
    text = text.split()[0]

    # чистим всё кроме букв
    text = re.sub(r"[^a-zа-я]", "", text)

    return text


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
            if len(clean.split()) >= 2:
                results.add(clean)

    return results

def build_capt_list_embed(guild: discord.Guild, capt_id: int):
    data = CAPT_DATA[capt_id]

    def fmt(users: dict[int, str | None], sort=False):
        if not users:
            return "—"

        lines = []

        items = (
            sort_main_by_tier(guild, users)
            if sort else users.items()
        )

        for uid, comment in items:
            member = guild.get_member(uid)
            if not member:
                continue

            tier = get_user_tier(member)
            tag = {
                "owner": "👑",
                "dep_owner": "⭐",
                "tier1": "🥇",
                "tier2": "🥈",
                "tier3": "🥉"
            }.get(tier, "👤")

            line = f"{tag} {member.mention}"
            if comment:
                line += f" — {comment}"

            lines.append(line)

        return "\n".join(lines)

    embed = discord.Embed(
        title="📋 Список на капт",
        color=discord.Color.blue()
    )
    embed.set_image(url="https://media.discordapp.net/attachments/675341437336027166/1014634234444521583/alliance2.gif?ex=697f1004&is=697dbe84&hm=a6d557da5d812193e658e2ce2624dcc77ed4c3569202d73e7e8d912d4be4f95c&")
    embed.add_field(
        name="🟢 Основной состав",
        value=fmt(data["main"], sort=True),
        inline=False
    )

    embed.add_field(
        name="🟡 Замена",
        value=fmt(data["reserve"]),
        inline=False
    )

    return embed


def sort_main_by_tier(guild: discord.Guild, main_dict: dict[int, str | None]):
    def priority(uid):
        member = guild.get_member(uid)
        if not member:
            return 99

        tier = get_user_tier(member)
        return {
            "owner": 0,
            "dep_owner": 1,
            "tier1": 2,
            "tier2": 3,
            "tier3": 4
        }.get(tier, 3)

    return sorted(main_dict.items(), key=lambda x: priority(x[0]))


def get_largest_voice_channel(guild: discord.Guild):
    voice_channels = [
        c for c in guild.voice_channels if len(c.members) > 0
    ]

    if not voice_channels:
        return None

    return max(voice_channels, key=lambda c: len(c.members))

def get_voice_names_from_channel(channel: discord.VoiceChannel) -> set[str]:
    names = set()
    for member in channel.members:
        if "|" in member.display_name:
            names.add(member.display_name.split("|", 1)[1].strip())
    return names


def numbered_list(items):
    if not items:
        return "—"
    return "\n".join(f"{i+1}. {item}" for i, item in enumerate(items))

def build_activity_embed(data):
    embed = discord.Embed(
        title="Отчёт актива",
        description=(
            f"**Комментарий:**\n{data['comment']}\n\n"
            f"**Игроков на скриншоте:** {data['players_total']}\n"
            f"**В голосовом канале:** {data['voice_count']}\n"
            f"**Канал:** {data['voice_channel']}"
        ),
        color=discord.Color.green(),
        timestamp=data["created_at"]
    )

    embed.add_field(
        name=f"✅ В игре и в войсе ({len(data['both'])})",
        value=numbered_list(sorted(data["both"])) or "—",
        inline=False
    )

    embed.add_field(
        name=f"❌ В игре, но не в войсе ({len(data['not_voice'])})",
        value=numbered_list(sorted(data["not_voice"])) or "—",
        inline=False
    )

    embed.add_field(
        name=f"✈️ IC-отпуск ({len(data['ic'])})",
        value=numbered_list(sorted(data["ic"])) or "—",
        inline=False
    )

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
    target_name = normalize_character_name(player_name)

    if not target_name:
        return None

    for channel in guild.channels:
        if not isinstance(channel, discord.TextChannel):
            continue

        if channel.category_id not in PLAYER_TICKET_CATEGORY_IDS:
            continue

        # daria-zinaida-alliance → ["daria", "zinaida", "alliance"]
        ticket_parts = channel.name.lower().split("-")

        if target_name in ticket_parts:
            return channel

    return None



def build_voice_top_embed(guild: discord.Guild):
    now = datetime.now(timezone.utc)

    temp_times = daily_voice_time.copy()

    for user_id, session in voice_sessions.items():
        delta = (now - session["joined_at"]).total_seconds()
        temp_times[user_id] = temp_times.get(user_id, 0) + int(delta)

    sorted_users = sorted(
        temp_times.items(),
        key=lambda x: x[1],
        reverse=True
    )[:10]

    embed = discord.Embed(
        title="ТОП-10 по активности за день",
        color=discord.Color.blue(),
        timestamp=datetime.now(MSK)
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

        lines.append(
            f"**{i}.** {member.display_name} — `{hours}ч {minutes}м {secs}с`"
        )

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
        embed.set_thumbnail(url=interaction.user.display_avatar.url)

        await thread.send(
            embed=embed,
            view=MeetingAbsenceApproveView(
                user_id=interaction.user.id,
                reason=self.reason.value
            )
        )

        await interaction.followup.send(
            "✅ Заявка отправлена",
            ephemeral=True
        )




class MeetingAbsenceApproveView(discord.ui.View):
    def __init__(self, user_id: int, reason: str):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.reason = reason

    @discord.ui.button(
        label="Одобрить",
        style=discord.ButtonStyle.success,
        custom_id="meeting_absence_approve"
    )
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not has_high_staff_role(interaction.user):
            return await interaction.response.send_message(
                "❌ Нет прав",
                ephemeral=True
            )

        MEETING_ABSENCE_DATA["approved"][self.user_id] = self.reason

        embed = interaction.message.embeds[0]
        embed.color = discord.Color.green()
        embed.description += (
            f"\n\n**Статус:** Одобрено"
            f"\n**Одобрил:** {interaction.user.display_name}"
        )

        for item in self.children:
            item.disabled = True

        await interaction.message.edit(embed=embed, view=self)

        member = interaction.guild.get_member(self.user_id)
        if member:
            try:
                await member.send(
                    "✅ Ваша заявка на отсутствие на собрании одобрена"
                )
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
            return await interaction.response.send_message(
                "❌ Нет прав",
                ephemeral=True
            )

        await interaction.response.send_modal(
            MeetingAbsenceRejectModal(
                message=interaction.message,
                user_id=self.user_id
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

        # ➕ В основной состав
        if self.action == "to_main":
            data["main"][uid] = comment
            await notify(uid, "🟢 Вы перенесены в **Основной состав**")

        # ➕ В замену
        elif self.action == "to_reserve":
            data["reserve"][uid] = comment
            await notify(uid, "🟡 Вы перенесены в **Замены**")

        # ➖ Из основного состава
        elif self.action == "from_main":
            if src != "main":
                await interaction.followup.send("❌ Игрок не в основном составе", ephemeral=True)
                return
            data["reserve"][uid] = comment
            await notify(uid, "🟡 Вы перенесены в **Замены**")

        await update_capt_list(interaction.guild, self.capt_id)



async def notify(user_id: int, text: str):
    user = bot.get_user(user_id)
    if user:
        try:
            await user.send(text)
        except:
            pass

class CaptManageView(discord.ui.View):
    def __init__(self, capt_id: int):
        super().__init__(timeout=None)
        self.capt_id = capt_id

    def staff_check(self, interaction):
        return has_owner_role(interaction.user)

    @discord.ui.button(label="➕ Мейн", style=discord.ButtonStyle.success)
    async def to_main(self, interaction, _):
        if not self.staff_check(interaction):
            return await interaction.response.send_message("❌ Нет прав", ephemeral=True)

        await interaction.response.send_modal(
            CaptMoveModal(self.capt_id, "to_main")
        )

    @discord.ui.button(label="➖ Мейн", style=discord.ButtonStyle.secondary)
    async def from_main(self, interaction, _):
        if not self.staff_check(interaction):
            return await interaction.response.send_message("❌ Нет прав", ephemeral=True)

        await interaction.response.send_modal(
            CaptMoveModal(self.capt_id, "from_main")
        )

    @discord.ui.button(label="🔒 Закрыть список", style=discord.ButtonStyle.danger)
    async def close(self, interaction, _):
        if not self.staff_check(interaction):
            return await interaction.response.send_message("❌ Нет прав", ephemeral=True)

        data = CAPT_DATA[self.capt_id]
        data["closed"] = True   # ← флаг

        # уведомления
        for uid in data["main"]:
            await notify(uid, "🔒 Список закрыт. Вы участвуете в капте.")

        channel = interaction.channel

        # 🔹 скрываем кнопки записи
        join_msg_id = data.get("join_message_id")
        if join_msg_id:
            try:
                join_msg = await channel.fetch_message(join_msg_id)
                await join_msg.edit(view=None)
            except:
                pass

        # 🔹 отключаем manage кнопки
        for item in self.children:
            item.disabled = True

        await interaction.message.edit(view=self)

        await interaction.response.send_message("🔒 Список закрыт", ephemeral=True)



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
        #content="@everyone",
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
                        return  # ✅ панель уже есть

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

    try:
        msg = await channel.fetch_message(msg_id)
    except discord.NotFound:
        return

    embed = build_capt_list_embed(guild, capt_id)
    await msg.edit(embed=embed)





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
        data = CAPT_DATA[self.capt_id]
        uid = interaction.user.id

        data["applied"].pop(uid, None)
        data["main"].pop(uid, None)
        data["reserve"].pop(uid, None)

        await update_capt_list(interaction.guild, self.capt_id)
        await interaction.response.send_message("❌ Вы выписались", ephemeral=True)

class CaptJoinModal(discord.ui.Modal, title="Запись на капт"):
    comment = discord.ui.TextInput(
        label="Комментарий (необязательно)",
        required=False
    )

    def __init__(self, capt_id):
        super().__init__()
        self.capt_id = capt_id

    async def on_submit(self, interaction: discord.Interaction):
        comment = self.comment.value.strip() or None
        data = CAPT_DATA[self.capt_id]
        uid = interaction.user.id

        # 🔹 убираем игрока из всех списков
        for key in ("main", "reserve", "applied"):
            data[key].pop(uid, None)

        tier = get_user_tier(interaction.user)

        # 🔹 если есть tier — основной состав
        if tier:
            data["main"][uid] = comment
            await notify(
                uid,
                f"🟢 Вы добавлены в **Основной состав ({tier.upper()})**"
            )
        else:
            # 🔹 без tier — сразу в замену
            data["reserve"][uid] = comment
            await notify(
                uid,
                "🟡 Вы добавлены в **Замену**"
            )

        await update_capt_list(interaction.guild, self.capt_id)
        await interaction.response.send_message("✅ Заявка принята", ephemeral=True)









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
        label="🔄 Запрос откатов",
        style=discord.ButtonStyle.primary,
        custom_id="discipline_rollback"
    )
    async def rollback(self, interaction, button):
        await interaction.response.send_modal(RollbackRequestModal())

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

        await report_channel.send(
            embed=embed,
            view=MeetingPunishView()
        )

        await interaction.response.send_message(
            "✅ Отчет о собрании отправлен!",
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

        await thread.send(
            content=(
                f"{interaction.user.mention} отправил(а) заявку "
                f"<@&{DISCIPLINE_ROLE_ID}>"
            ),
            embed=embed,
            view=ICApproveView(
                user_id=interaction.user.id,
                duration_minutes=int(self.duration.value)
            )
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

    def __init__(self, punished_member_id: int, message_link: str):
        super().__init__()
        self.punished_member_id = punished_member_id
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
            title="⚖️ Обжалование наказания",
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc)
        )

        embed.add_field(
            name="Игрок",
            value=f"{interaction.user.mention}\nID: {interaction.user.id}",
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
    def __init__(self, punished_member_id: int):
        super().__init__(timeout=None)
        self.punished_member_id = punished_member_id

    @discord.ui.button(
        label="Обжаловать наказание",
        style=discord.ButtonStyle.secondary,
        emoji="⚖️",
        custom_id="appeal_button"
    )
    async def appeal(self, interaction: discord.Interaction, button: discord.ui.Button):

        if interaction.user.id != self.punished_member_id:
            await interaction.response.send_message(
                "❌ Вы не можете обжаловать чужое наказание",
                ephemeral=True
            )
            return

        message_link = interaction.message.jump_url

        await interaction.response.send_modal(
            AppealModal(
                punished_member_id=self.punished_member_id,
                message_link=message_link
            )
        )

    @discord.ui.button(
        label="Обжалование с док-вом",
        style=discord.ButtonStyle.primary,
        emoji="📎",
        custom_id="appeal_with_proof"
    )
    async def appeal_with_proof(self, interaction: discord.Interaction, button: discord.ui.Button):

        if interaction.user.id != self.punished_member_id:
            await interaction.response.send_message(
                "❌ Вы не можете обжаловать чужое наказание",
                ephemeral=True
            )
            return

        await interaction.response.send_modal(
            AppealWithProofModal(
                punished_member_id=self.punished_member_id,
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
                    f"✅ Ваше обжалование **ОДОБРЕНО**!\n\n"
                    f"Модератор: {interaction.user.mention}"
                )

            except discord.Forbidden:
                print(f"Не удалось отправить ЛС {user_id}")

            except discord.NotFound:
                print(f"Юзер {user_id} вышел с сервера")

        # отключаем кнопки
        for item in self.children:
            item.disabled = True

        await msg.edit(embed=embed, view=self)

        await interaction.response.send_message(
            "✅ Обжалование одобрено",
            ephemeral=True
        )

    # ================= REJECT =================

    @discord.ui.button(
        label="Отклонить",
        style=discord.ButtonStyle.danger,
        emoji="❌",
        custom_id="appeal_reject"
    )
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):

        # открываем модалку с причиной
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

        # 🔥 ОБЯЗАТЕЛЬНО
        await interaction.response.defer(ephemeral=True)

        msg = self.message
        embed = msg.embeds[0]

        embed.color = discord.Color.red()

        embed.add_field(
            name="Решение",
            value=(
                f"❌ Обжалование отклонено {interaction.user.mention}\n"
                f"**Причина:** {self.reason.value}"
            ),
            inline=False
        )

        # получаем ID игрока
        user_id = get_user_id_from_embed(embed)

        if user_id:
            try:
                member = await interaction.guild.fetch_member(user_id)

                await member.send(
                    f"❌ Ваше обжалование **ОТКЛОНЕНО**\n\n"
                    f"📌 Причина:\n{self.reason.value}\n\n"
                    f"Модератор: {interaction.user.mention}"
                )

            except discord.Forbidden:
                print(f"[APPEAL] ЛС закрыты: {user_id}")
            except discord.NotFound:
                print(f"[APPEAL] Юзер вышел: {user_id}")

        # отключаем кнопки
        view = discord.ui.View.from_message(msg)
        for item in view.children:
            item.disabled = True

        await msg.edit(embed=embed, view=view)

        # ✅ ТОЛЬКО followup
        await interaction.followup.send(
            "❌ Обжалование отклонено",
            ephemeral=True
        )







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

        # 🔔 Уведомляем пользователя
        member = interaction.guild.get_member(self.user_id)

        if member:
            try:
                await member.send(
                    f"❌ Ваш IC-отпуск отклонён.\n"
                    f"Причина: {self.reason.value}"
                )
            except discord.Forbidden:
                pass  # ЛС закрыты

        await interaction.response.send_message(
            "❌ Заявка отклонена",
            ephemeral=True
        )




class ICApproveView(discord.ui.View):
    def __init__(self, user_id: int, duration_minutes: int):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.duration_minutes = duration_minutes

    @discord.ui.button(
        label="Одобрить",
        style=discord.ButtonStyle.success,
        custom_id="ic_approve"
    )
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):

        member = interaction.user
        if not isinstance(member, discord.Member) or not has_high_staff_role(member):
            await interaction.response.send_message(
                "❌ У вас нет прав для одобрения IC-отпуска",
                ephemeral=True
            )
            return

        until = datetime.now(timezone.utc) + timedelta(minutes=self.duration_minutes)

        ic_vacations[self.user_id] = {
            "until": until,
            "approved_by": interaction.user.id
        }

        embed = interaction.message.embeds[0]
        embed.color = discord.Color.green()

        embed.description += (
            f"\n\n**Статус:** Одобрено"
            f"\n**Одобрил:** {interaction.user.display_name}"
            f"\n**До:** {until.astimezone(MSK).strftime('%d.%m.%Y %H:%M МСК')}"
        )

        for item in self.children:
            item.disabled = True

        await interaction.message.edit(embed=embed, view=self)

        user = interaction.client.get_user(self.user_id)
        if user:
            await user.send(
                f"Ваш IC-отпуск одобрен до "
                f"{until.astimezone(MSK).strftime('%H:%M МСК')}"
            )

        await interaction.response.send_message("✅ Заявка одобрена", ephemeral=True)



    @discord.ui.button(
    label="Отклонить",
    style=discord.ButtonStyle.danger,
    custom_id="ic_reject"
    )
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):

        member = interaction.user
        if not isinstance(member, discord.Member) or not has_high_staff_role(member):
            await interaction.response.send_message(
                "❌ У вас нет прав для отклонения IC-отпуска",
                ephemeral=True
            )
            return

        await interaction.response.send_modal(
            ICRejectReasonModal(
                message=interaction.message,
                user_id=self.user_id
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




class RollbackEditView(discord.ui.View):
    def __init__(self, request_key: str):
        super().__init__(timeout=None)
        self.request_key = request_key

    @discord.ui.button(
        label="✏️ Изменить откат",
        style=discord.ButtonStyle.secondary,
        custom_id="ch_rollback"
    )
    async def edit(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(
            RollbackLinkModal(
                request_key=self.request_key,
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
        req = ROLLBACK_REQUESTS.get(self.request_key)
        if not req:
            await interaction.response.send_message(
                "❌ Запрос не найден",
                ephemeral=True
            )
            return

        data = req["players"].get(self.channel_id)
        if not data:
            await interaction.response.send_message(
                "❌ Данные игрока не найдены",
                ephemeral=True
            )
            return

        data["link"] = self.link.value

        channel = interaction.channel
        msg = await channel.fetch_message(data["message_id"])

        embed = msg.embeds[0]

        embed.clear_fields()
        embed.add_field(
            name="Откат",
            value=self.link.value,
            inline=False
        )

        await msg.edit(
            embed=embed,
            view=RollbackEditView(self.request_key)
        )

        await interaction.response.send_message(
            "✅ Откат сохранён",
            ephemeral=True
        )
class RollbackLinkView(discord.ui.View):
    def __init__(self, request_key: str):
        super().__init__(timeout=None)
        self.request_key = request_key

    @discord.ui.button(
        label="Прикрепить откат",
        style=discord.ButtonStyle.primary,
        custom_id="at_rollback"
    )
    async def attach(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(
            RollbackLinkModal(
                request_key=self.request_key,
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
            )

            await punish_channel.send(
                text,
                view=AppealView(member.id)
            )

            issued += 1

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
        label="🔴 Выдать выговор",
        style=discord.ButtonStyle.danger,
        custom_id="meeting_reprimand"
    )
    async def reprimand(self, interaction: discord.Interaction, button: discord.ui.Button):

        guild = interaction.guild
        reprimand_role = guild.get_role(REPRIMAND_ROLE_ID)
        punish_channel = guild.get_channel(PUNISH_CHANNEL_ID)
        activity_channel = guild.get_channel(ACTIVITY_REPORT_CHANNEL_ID)

        if not reprimand_role or not punish_channel or not activity_channel:
            await interaction.response.send_message(
                "❌ Ошибка конфигурации каналов или ролей",
                ephemeral=True
            )
            return

        present, absent = get_meeting_attendance(guild)

        approved_ids = set(MEETING_ABSENCE_DATA["approved"].keys())

        absent = [m for m in absent if m.id not in approved_ids]

        if not absent:
            await interaction.response.send_message(
                "✅ Нет нарушителей (все либо пришли, либо имеют одобренную заявку)",
                ephemeral=True
            )
            return


        issued = 0

        for member in absent:
            if reprimand_role in member.roles:
                continue

            try:
                # 1️⃣ выдаём роль
                await member.add_roles(
                    reprimand_role,
                    reason="Неявка на собрание семьи"
                )

                # 2️⃣ пишем пасту в канал наказаний
                text = (
                    f"1. {member.mention}\n"
                    f"2. **2.7** Запрещена неявка на собрание семьи без предупреждения в своем тикете. "
                    f"I  Выговор [1/2]\n"
                    f"3. {activity_channel.mention}"
                )

                await punish_channel.send(
                    text,
                    view=AppealView(punished_member_id=member.id)
                )
                issued += 1

            except Exception:
                continue

        await interaction.response.send_message(
            f"🔴 Выговор выдан **{issued}** участникам",
            ephemeral=True
        )

        # 🔒 блокируем повторное нажатие
        button.disabled = True
        await interaction.message.edit(view=self)


class MovePlayerSelect(discord.ui.View):
    def __init__(self, channel_id: int, mode: str):
        super().__init__(timeout=60)
        self.channel_id = channel_id
        self.mode = mode

        data = LAST_ACTIVITY_REPORT.get(channel_id)
        if not data:
            return

        source = data["not_voice"] if mode == "voice" else data["ic"]

        self.select = discord.ui.Select(
            placeholder="Выбери игрока",
            options=[
                discord.SelectOption(label=name)
                for name in sorted(source)
            ]
        )
        self.select.callback = self.on_select
        self.add_item(self.select)

    async def on_select(self, interaction: discord.Interaction):

        if not has_high_staff_role(interaction.user):
            await interaction.response.send_message(
                "❌ У вас нет прав на редактирование отчёта",
                ephemeral=True
            )
            return


        raw_name = self.select.values[0]
        data = LAST_ACTIVITY_REPORT[self.channel_id]

        clean = clean_player_name(raw_name)
        new_value = f"✅ {clean}"

        if self.mode == "voice":
            data["not_voice"].remove(raw_name)
            data["both"].add(new_value)
        else:
            data["ic"].remove(raw_name)
            data["both"].add(new_value)

        channel = interaction.guild.get_channel(self.channel_id)
        msg = await channel.fetch_message(data["message_id"])

        embed = build_activity_embed(data)
        await msg.edit(embed=embed)

        await interaction.response.edit_message(
            content=f"✅ **{clean}** перемещён в «В игре и в войсе»",
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
            await interaction.response.send_message(
                "❌ У вас нет прав",
                ephemeral=True
            )
            return

        data = LAST_ACTIVITY_REPORT.get(self.channel_id)
        if not data:
            await interaction.response.send_message(
                "❌ Отчёт не найден",
                ephemeral=True
            )
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
            await interaction.response.send_message(
                f"❌ **{entered}** не найден в списке",
                ephemeral=True
            )
            return

        clean = clean_player_name(found)
        new_value = f"✅ {clean}"

        source.remove(found)
        data["both"].add(new_value)

        channel = interaction.guild.get_channel(self.channel_id)
        msg = await channel.fetch_message(data["message_id"])
        await msg.edit(embed=build_activity_embed(data))

        await interaction.response.send_message(
            f"✅ **{clean}** перенесён в «В игре и в войсе»",
            ephemeral=True
        )





# ================== BOT ==================

class Bot(discord.Client):
    def __init__(self, *, intents: discord.Intents):
        super().__init__(intents=intents)
        self.voice_initialized = False

    async def setup_hook(self):
        self.add_view(ICRequestView())
        self.add_view(FamilyRequestView())
        self.add_view(MeetingAbsencePanelView())
        self.add_view(MeetingAbsenceApproveView(user_id=0, reason=""))
        self.add_view(AppealManageView())
        self.add_view(AppealView(0))
        self.add_view(DisciplinePanelView())
        self.add_view(CaptPanelView())



    async def daily_voice_top_task(self):
        await self.wait_until_ready()

        while not self.is_closed():
            now = datetime.now(MSK)

            # время следующего запуска — 23:59
            target = now.replace(hour=23, minute=59, second=0, microsecond=0)
            if now >= target:
                target += timedelta(days=1)

            sleep_seconds = (target - now).total_seconds()
            await asyncio.sleep(sleep_seconds)

            for guild in self.guilds:
                channel = guild.get_channel(VOICE_TOP_CHANNEL_ID)
                if not channel:
                    continue

                embed = build_voice_top_embed(guild)
                await channel.send(embed=embed)

            # 🧹 ОБНУЛЕНИЕ ПОСЛЕ ТОПА
            daily_voice_time.clear()

            now_utc = datetime.now(timezone.utc)

            # перезапускаем активные сессии
            for uid, session in list(voice_sessions.items()):
                voice_sessions[uid]["joined_at"] = now_utc



    async def ic_cleanup(self):
        await self.wait_until_ready()
        while not self.is_closed():
            now = datetime.now(timezone.utc)
            expired = [u for u, d in ic_vacations.items() if d["until"] <= now]
            for u in expired:
                del ic_vacations[u]
            await asyncio.sleep(60)

    async def on_ready(self):
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

                    # пропускаем AFK канал
                    if guild.afk_channel and channel.id == guild.afk_channel.id:
                        continue

                    for member in channel.members:

                        if member.bot:
                            continue

                        if member.voice and not member.voice.self_deaf and not member.voice.deaf:

                            voice_sessions[member.id] = {
                                "channel_id": channel.id,
                                "joined_at": now
                            }

                            print(f"[VOICE INIT] {member.display_name}")

            self.voice_initialized = True
            self.loop.create_task(self.daily_voice_top_task())

    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState
    ):
        if member.bot:
            return

        now = datetime.now(timezone.utc)

        def stop_session():
            session = voice_sessions.pop(member.id, None)
            if not session:
                return

            delta = (now - session["joined_at"]).total_seconds()
            daily_voice_time[member.id] = daily_voice_time.get(member.id, 0) + int(delta)

        # ====== ЕСЛИ СЕССИЯ БЫЛА, НО ТЕПЕРЬ НЕЛЬЗЯ СЧИТАТЬ ======
        if member.id in voice_sessions:
            if (
                after.channel is None                     
                or after.self_deaf                        
                or after.deaf                             
                or after.channel == member.guild.afk_channel
            ):
                stop_session()
                return

        # ====== НАЧАЛО СЕССИИ ======
        if (
            after.channel
            and not after.self_deaf
            and not after.deaf
            and after.channel != member.guild.afk_channel
        ):
            if member.id not in voice_sessions:
                voice_sessions[member.id] = {
                    "channel_id": after.channel.id,
                    "joined_at": now
                }

    async def on_message(self, message: discord.Message):

        if message.author.bot:
            return

        user_id = message.author.id
        content = message.content.strip()
        now = datetime.now(timezone.utc)

        # ==================================================
        # 🔥 APEAL WITH PROOF — ОБЯЗАТЕЛЬНО САМЫЙ ВЕРХ
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
                value=f"{message.author.mention}\nID: {message.author.id}",
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
        # ⚔️ FAMILY WAR — CAPT SCREENSHOT
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

            if content in ROLLBACK_REQUESTS:
                req = ROLLBACK_REQUESTS[content]

                lines = []
                for p in req["players"].values():
                    status = "✅" if p["link"] else "❌"
                    lines.append(f"{status} {p['name']} — <#{p['ticket_id']}>")

                embed = discord.Embed(
                    title="Отчёт по откатам",
                    description=f"**Комментарий:**\n{content}\n\n" + "\n".join(lines),
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
                        all_game_names |= extract_game_names(tmp.name)

            if not all_game_names:
                return

            try:
                await message.delete()
            except:
                pass

            ROLLBACK_REQUESTS[content] = {
                "players": {},
                "created_by": message.author.id,
                "created_at": now
            }

            for name in all_game_names:
                ticket = find_ticket_by_player(message.guild, name)
                if not ticket:
                    continue

                embed = discord.Embed(
                    title="Запрос отката",
                    description=f"**Комментарий:**\n{content}",
                    color=discord.Color.orange()
                )

                msg = await ticket.send(embed=embed, view=RollbackLinkView(content))

                ROLLBACK_REQUESTS[content]["players"][ticket.id] = {
                    "name": name,
                    "ticket_id": ticket.id,
                    "message_id": msg.id,
                    "link": None
                }

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

        if not all_game_names:
            return

        try:
            await message.delete()
        except:
            pass

        largest_voice = get_largest_voice_channel(message.guild)

        if largest_voice:
            voice_names = {m.display_name for m in largest_voice.members}
            voice_count = len(largest_voice.members)
            voice_channel_name = largest_voice.name
        else:
            voice_names = set()
            voice_count = 0
            voice_channel_name = "—"

        voice_norm = {normalize_name(v) for v in voice_names}

        active_ic = {u: d for u, d in ic_vacations.items() if d["until"] > now}

        both, not_voice, ic_players = [], [], []

        for g in sorted(all_game_names):
            norm = normalize_name(g)

            ic_match = False
            for uid, d in active_ic.items():
                member = message.guild.get_member(uid)
                if member and names_match(member.display_name, g):
                    ic_players.append(
                        f"✈️ {g} (до {d['until'].astimezone(MSK).strftime('%H:%M')})"
                    )
                    ic_match = True
                    break

            if ic_match:
                continue

            if norm in voice_norm:
                both.append(f"✅ {g}")
            else:
                not_voice.append(f"❌ {g}")

        embed = build_activity_embed({
            "comment": comment,
            "players_total": len(all_game_names),
            "voice_count": voice_count,
            "voice_channel": voice_channel_name,
            "both": both,
            "not_voice": not_voice,
            "ic": ic_players,
            "created_at": now
        })

        report_channel = message.guild.get_channel(ACTIVITY_REPORT_CHANNEL_ID)

        msg = await report_channel.send(
            embed=embed,
            view=ActivityControlView(report_channel.id)
        )

        LAST_ACTIVITY_REPORT[report_channel.id] = {
            "message_id": msg.id,
            "both": set(both),
            "not_voice": set(not_voice),
            "ic": set(ic_players),
            "players_total": len(all_game_names),
            "voice_count": voice_count,
            "voice_channel": voice_channel_name,
            "comment": comment,
            "created_at": now
        }







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
        embed.add_field(name="Пользователь", value=member.mention, inline=False)
        embed.add_field(name="ID пользователя", value=str(member.id), inline=False)
        embed.add_field(name="Никнейм", value=member.display_name, inline=True)
        embed.add_field(
            name="Время входа",
            value=now.strftime("%d.%m.%Y %H:%M:%S"),
            inline=True
        )

        await channel.send(embed=embed)

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
        embed.add_field(name="Пользователь", value=member.mention, inline=False)
        embed.add_field(name="ID пользователя", value=str(member.id), inline=False)
        embed.add_field(name="Никнейм", value=member.display_name, inline=True)
        embed.add_field(
            name="Время выхода",
            value=now.strftime("%d.%m.%Y %H:%M:%S"),
            inline=True
        )

        await channel.send(embed=embed)

class FamilyApproveView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    def get_user_id(self, embed):
        return int(embed.footer.text.split(":")[1])

    @discord.ui.button(label="✅ Одобрить", style=discord.ButtonStyle.success)
    async def approve(self, interaction: discord.Interaction, button):
        embed = interaction.message.embeds[0]
        uid = self.get_user_id(embed)

        embed.color = discord.Color.green()
        embed.add_field(
            name="📌 Решение",
            value=f"✅ Одобрено {interaction.user.mention}",
            inline=False
        )

        user = interaction.client.get_user(uid)
        if user:
            await user.send("✅ Ваша заявка одобрена, с вами скоро свяжутся")

        await interaction.message.edit(
            embed=embed,
            view=FamilyProcessView()
        )

        await interaction.response.send_message("Заявка одобрена", ephemeral=True)

    @discord.ui.button(label="❌ Отклонить", style=discord.ButtonStyle.danger)
    async def reject(self, interaction: discord.Interaction, button):
        embed = interaction.message.embeds[0]
        uid = self.get_user_id(embed)

        embed.color = discord.Color.red()
        embed.add_field(
            name="📌 Решение",
            value=f"❌ Отклонено {interaction.user.mention}",
            inline=False
        )

        user = interaction.client.get_user(uid)
        if user:
            await user.send(
                f"❌ Ваша заявка отклонена куратором {interaction.user.mention}"
            )

        await interaction.message.edit(embed=embed, view=None)
        await interaction.response.send_message("Заявка отклонена", ephemeral=True)

class FamilyProcessView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    def get_user_id(self, embed):
        return int(embed.footer.text.split(":")[1])

    @discord.ui.button(label="🕓 В работе", style=discord.ButtonStyle.secondary)
    async def in_work(self, interaction: discord.Interaction, button):
        embed = interaction.message.embeds[0]
        uid = self.get_user_id(embed)

        embed.add_field(
            name="📌 Статус",
            value=f"🕓 В работе у {interaction.user.mention}",
            inline=False
        )

        user = interaction.client.get_user(uid)
        if user:
            await user.send(
                f"🕓 Вашу заявку взял в работу {interaction.user.mention}"
            )

        await interaction.message.edit(embed=embed)
        await interaction.response.send_message("Заявка взята в работу", ephemeral=True)

    @discord.ui.button(label="✅ Принять", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button):
        embed = interaction.message.embeds[0]
        uid = self.get_user_id(embed)

        embed.color = discord.Color.green()
        embed.add_field(
            name="🏆 Итог",
            value=f"✅ Принят в семью ({interaction.user.mention})",
            inline=False
        )

        user = interaction.client.get_user(uid)
        if user:
            await user.send("🎉 Ваша заявка в семью принята, поздравляем!")

        await interaction.message.edit(embed=embed, view=None)
        await interaction.response.send_message("Игрок принят", ephemeral=True)

    @discord.ui.button(label="❌ Отказать", style=discord.ButtonStyle.danger)
    async def deny(self, interaction: discord.Interaction, button):
        embed = interaction.message.embeds[0]
        uid = self.get_user_id(embed)

        embed.color = discord.Color.red()
        embed.add_field(
            name="🏁 Итог",
            value=f"❌ Отказ ({interaction.user.mention})",
            inline=False
        )

        user = interaction.client.get_user(uid)
        if user:
            await user.send("❌ Ваша заявка в семью отклонена")

        await interaction.message.edit(embed=embed, view=None)
        await interaction.response.send_message("Заявка отклонена", ephemeral=True)


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

        embed = discord.Embed(
            title="📥 Новая заявка в семью",
            color=discord.Color.gold(),
            timestamp=datetime.now(timezone.utc)
        )

        embed.set_thumbnail(url=interaction.user.display_avatar.url)

        embed.add_field(name="👤 **Тег:**", value=interaction.user.mention, inline=False)
        embed.add_field(name="📄 **Данные:**", value=self.name.value, inline=False)
        embed.add_field(name="🕓 **Средний онлайн:**", value=self.online.value, inline=False)
        embed.add_field(name="🏠 **Предыдущие семьи:**", value=self.families.value or "—", inline=False)
        embed.add_field(name="🔎 **Откуда узнал:**", value=self.source.value, inline=False)
        embed.add_field(name="🎯 **Откаты:**", value=self.skills.value, inline=False)

        embed.add_field(name="📌 Статус", value="⏳ На рассмотрении", inline=False)
        embed.set_footer(text=f"applicant:{interaction.user.id}")

        await channel.send(
            embed=embed,
            view=FamilyApproveView()
        )

        await interaction.followup.send(
            "✅ Ваша заявка отправлена и находится на рассмотрении",
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
