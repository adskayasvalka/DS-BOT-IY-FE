import discord
from discord import app_commands
from discord.ext import commands
import json
import os
from datetime import datetime, timedelta
import asyncio

TOKEN = "MTU1NzM5OTU0MjY3NTI4NDA1OA.G_CykN.MO3rL7nDi7Lnv67ND6nsoPajWGZbqOM-VpJ2QM"
DATA_FILE = "data.json"

# ================== КОНФИГ ==================
ROLE_FULL = 1435260764381380799
ROLE_FULL2 = 1436600017334042675
ROLE_FULL_NO_TEXT_1 = 1441431326413684776
ROLE_FULL_NO_TEXT_2 = 1441432137176715305
ROLE_NO_BAN_TEXT = 1441432378764558367      # без банов и текст
ROLE_NO_BAN_KICK_TEXT = 1441432477553135701 # без банов, киков и текст
ROLE_INTERN = 1441432671657132115           # стажёр — без банов, киков, без текст
ROLE_APPEAL_STAFF = 1441432731195281534     # для тикетов жалоб/апелляций

DONATE_CHANNEL = 1557309302371393536
COMPLAINT_CHANNEL = 1426813335176740945
APPEAL_CHANNEL = 1426813381934977155

ALL_STAFF_ROLES = [
    ROLE_FULL, ROLE_FULL2,
    ROLE_FULL_NO_TEXT_1, ROLE_FULL_NO_TEXT_2,
    ROLE_NO_BAN_TEXT, ROLE_NO_BAN_KICK_TEXT, ROLE_INTERN
]

# ================== БАЗА ДАННЫХ ==================
def load_data():
    if not os.path.exists(DATA_FILE):
        return {"warns": {}, "punishments": {}, "tickets": {}}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

DATA = load_data()

# ================== БОТ ==================
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree


# ================== ПРОВЕРКИ ПРАВ ==================
def has_any_role(member: discord.Member, role_ids):
    return any(r.id in role_ids for r in member.roles)

def can_use_mod(member: discord.Member):
    return has_any_role(member, ALL_STAFF_ROLES)

def can_ban(member: discord.Member):
    # Полный доступ + без текст (роли у которых есть баны)
    allowed = {ROLE_FULL, ROLE_FULL2, ROLE_FULL_NO_TEXT_1, ROLE_FULL_NO_TEXT_2}
    return has_any_role(member, allowed)

def can_kick(member: discord.Member):
    allowed = {ROLE_FULL, ROLE_FULL2, ROLE_FULL_NO_TEXT_1, ROLE_FULL_NO_TEXT_2, ROLE_NO_BAN_TEXT}
    return has_any_role(member, allowed)

def can_mute(member: discord.Member):
    return can_use_mod(member)

def can_warn(member: discord.Member):
    return can_use_mod(member)

def can_text(member: discord.Member):
    # "текст" доступен всем кроме ролей "без текст" и стажёра
    denied = {ROLE_FULL_NO_TEXT_1, ROLE_FULL_NO_TEXT_2, ROLE_NO_BAN_TEXT, ROLE_NO_BAN_KICK_TEXT, ROLE_INTERN}
    if has_any_role(member, denied) and not has_any_role(member, {ROLE_FULL, ROLE_FULL2}):
        return False
    return can_use_mod(member)

def is_ticket_staff(member: discord.Member):
    return has_any_role(member, {ROLE_APPEAL_STAFF, ROLE_FULL})


# ================== ПАНЕЛЬ ПРАЙСА ==================
class DonateView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        prices = [
            ("Модератор", "500₽"),
            ("Старший Модератор", "1000₽"),
            ("Главный Модератор", "1500₽"),
            ("Администратор", "2000₽"),
            ("Старший Администратор", "3000₽"),
            ("Главный Администратор", "4000₽"),
        ]
        for name, price in prices:
            self.add_item(DonateButton(name, price))


class DonateButton(discord.ui.Button):
    def __init__(self, name, price):
        super().__init__(label=f"{name} — {price}", style=discord.ButtonStyle.primary, custom_id=f"donate_{name}")
        self.name = name
        self.price = price

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            f"Вы выбрали привилегию **{self.name}** за **{self.price}**.\n"
            f"Свяжитесь с администрацией для оформления покупки.",
            ephemeral=True
        )


# ================== ТИКЕТЫ (жалобы/апелляции) ==================
class ComplaintModal(discord.ui.Modal, title="Подать жалобу"):
    nickname = discord.ui.TextInput(label="Никнейм нарушителя (Discord)", required=True, max_length=100)
    violation = discord.ui.TextInput(label="Что он нарушил?", style=discord.TextStyle.paragraph, required=True, max_length=1000)
    evidence = discord.ui.TextInput(label="Фото/видео доказательства (ссылки)", style=discord.TextStyle.paragraph, required=False, max_length=1000)

    async def on_submit(self, interaction: discord.Interaction):
        await create_ticket(
            interaction,
            kind="Жалоба",
            fields=[
                ("Никнейм нарушителя", self.nickname.value),
                ("Нарушение", self.violation.value),
                ("Доказательства", self.evidence.value or "Не предоставлены"),
            ],
            staff_role_ids=[ROLE_APPEAL_STAFF, ROLE_FULL],
        )


class AppealModal(discord.ui.Modal, title="Подать апелляцию"):
    nickname = discord.ui.TextInput(label="Ваш никнейм (Discord)", required=True, max_length=100)
    who = discord.ui.TextInput(label="Кто выдал наказание?", required=True, max_length=200)
    reason = discord.ui.TextInput(label="Причина наказания", style=discord.TextStyle.paragraph, required=True, max_length=1000)
    evidence = discord.ui.TextInput(label="Доказательства невиновности", style=discord.TextStyle.paragraph, required=False, max_length=1000)

    async def on_submit(self, interaction: discord.Interaction):
        await create_ticket(
            interaction,
            kind="Апелляция",
            fields=[
                ("Никнейм", self.nickname.value),
                ("Кто выдал наказание", self.who.value),
                ("Причина наказания", self.reason.value),
                ("Доказательства невиновности", self.evidence.value or "Не предоставлены"),
            ],
            staff_role_ids=[ROLE_FULL_NO_TEXT_1, ROLE_FULL_NO_TEXT_2, ROLE_FULL],
        )


async def create_ticket(interaction: discord.Interaction, kind: str, fields, staff_role_ids):
    guild = interaction.guild
    user = interaction.user
    category = interaction.channel.category

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
    }
    for rid in staff_role_ids:
        role = guild.get_role(rid)
        if role:
            overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

    channel_name = f"{'жалоба' if kind == 'Жалоба' else 'апелляция'}-{user.name}".lower().replace(" ", "-")[:90]

    try:
        ticket_channel = await guild.create_text_channel(
            name=channel_name, category=category, overwrites=overwrites
        )
    except Exception as e:
        await interaction.response.send_message(f"Ошибка при создании канала: {e}", ephemeral=True)
        return

    embed = discord.Embed(
        title=f"{kind}: {user}",
        description=f"Ваш тикет создан и будет рассмотрен в ближайшее время.\nНе создавайте лишних сообщений — ожидайте ответа персонала.",
        color=discord.Color.orange(),
        timestamp=datetime.utcnow()
    )
    embed.add_field(name="Автор", value=user.mention, inline=False)
    for name, value in fields:
        embed.add_field(name=name, value=value or "—", inline=False)

    await ticket_channel.send(content=user.mention, embed=embed, view=CloseTicketView())

    await interaction.response.send_message(f"Ваш тикет создан: {ticket_channel.mention}", ephemeral=True)


class CloseTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Закрыть тикет", style=discord.ButtonStyle.danger, custom_id="close_ticket_btn")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_ticket_staff(interaction.user):
            await interaction.response.send_message("У вас нет прав на закрытие тикета.", ephemeral=True)
            return
        await interaction.response.send_message("Тикет будет удалён через 5 секунд...", ephemeral=False)
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete()
        except Exception:
            pass


class ComplaintView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Подать жалобу", style=discord.ButtonStyle.danger, custom_id="open_complaint")
    async def open_complaint(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ComplaintModal())


class AppealView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Подать апелляцию", style=discord.ButtonStyle.primary, custom_id="open_appeal")
    async def open_appeal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AppealModal())


# ================== МОДАЛКА ДЛЯ ТЕКСТА ==================
class TextModal(discord.ui.Modal, title="Отправить текст от имени бота"):
    content = discord.ui.TextInput(
        label="Текст сообщения",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=4000,
        placeholder="Введите текст (до 4000 символов)..."
    )

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(description=self.content.value, color=discord.Color.blurple())
        await interaction.channel.send(embed=embed)
        await interaction.response.send_message("Текст отправлен.", ephemeral=True)


# ================== ПАНЕЛЬ ПРОФИЛЯ ==================
class ProfileView(discord.ui.View):
    def __init__(self, member: discord.Member):
        super().__init__(timeout=180)
        self.member = member

    @discord.ui.button(label="Снять предупреждение", style=discord.ButtonStyle.success, custom_id="p_unwarn")
    async def unwarn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not can_use_mod(interaction.user):
            await interaction.response.send_message("Нет прав.", ephemeral=True)
            return
        uid = str(self.member.id)
        if DATA["warns"].get(uid):
            DATA["warns"][uid].pop()
            save_data(DATA)
            await interaction.response.send_message("Последнее предупреждение снято.", ephemeral=True)
        else:
            await interaction.response.send_message("У пользователя нет предупреждений.", ephemeral=True)

    @discord.ui.button(label="Выдать предупреждение", style=discord.ButtonStyle.primary, custom_id="p_warn")
    async def warn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not can_warn(interaction.user):
            await interaction.response.send_message("Нет прав.", ephemeral=True)
            return
        await interaction.response.send_modal(WarnModal(self.member))

    @discord.ui.button(label="Мут", style=discord.ButtonStyle.secondary, custom_id="p_mute")
    async def mute(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not can_mute(interaction.user):
            await interaction.response.send_message("Нет прав.", ephemeral=True)
            return
        try:
            until = datetime.utcnow() + timedelta(minutes=10)
            await self.member.timeout(until, reason=f"Мут от {interaction.user}")
            log_punishment(self.member.id, f"Мут 10 минут ({interaction.user})")
            await interaction.response.send_message("Пользователь замучен на 10 минут.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Ошибка: {e}", ephemeral=True)

    @discord.ui.button(label="Кик", style=discord.ButtonStyle.danger, custom_id="p_kick")
    async def kick(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not can_kick(interaction.user):
            await interaction.response.send_message("Нет прав.", ephemeral=True)
            return
        try:
            await self.member.kick(reason=f"Кик от {interaction.user}")
            log_punishment(self.member.id, f"Кик ({interaction.user})")
            await interaction.response.send_message("Пользователь кикнут.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Ошибка: {e}", ephemeral=True)

    @discord.ui.button(label="Бан", style=discord.ButtonStyle.danger, custom_id="p_ban")
    async def ban(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not can_ban(interaction.user):
            await interaction.response.send_message("Нет прав.", ephemeral=True)
            return
        try:
            await self.member.ban(reason=f"Бан от {interaction.user}")
            log_punishment(self.member.id, f"Бан ({interaction.user})")
            await interaction.response.send_message("Пользователь забанен.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Ошибка: {e}", ephemeral=True)


class WarnModal(discord.ui.Modal, title="Выдать предупреждение"):
    reason = discord.ui.TextInput(label="Причина", required=True, max_length=300)

    def __init__(self, member: discord.Member):
        super().__init__()
        self.member = member

    async def on_submit(self, interaction: discord.Interaction):
        uid = str(self.member.id)
        DATA["warns"].setdefault(uid, []).append({
            "reason": self.reason.value,
            "moderator": str(interaction.user),
            "date": datetime.utcnow().strftime("%Y-%m-%d %H:%M")
        })
        log_punishment(self.member.id, f"Предупреждение: {self.reason.value} ({interaction.user})")
        save_data(DATA)
        await interaction.response.send_message("Предупреждение выдано.", ephemeral=True)


def log_punishment(user_id, text):
    uid = str(user_id)
    DATA["punishments"].setdefault(uid, []).append({
        "text": text,
        "date": datetime.utcnow().strftime("%Y-%m-%d %H:%M")
    })
    save_data(DATA)


def build_profile_embed(member: discord.Member) -> discord.Embed:
    uid = str(member.id)
    warns = DATA["warns"].get(uid, [])
    puns = DATA["punishments"].get(uid, [])

    embed = discord.Embed(title=f"Профиль: {member}", color=discord.Color.blue(), timestamp=datetime.utcnow())
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="ID", value=member.id, inline=False)
    embed.add_field(name="Предупреждений", value=str(len(warns)), inline=True)
    embed.add_field(name="Наказаний всего", value=str(len(puns)), inline=True)
    embed.add_field(name="Аккаунт создан", value=member.created_at.strftime("%Y-%m-%d"), inline=False)
    embed.add_field(name="Присоединился", value=member.joined_at.strftime("%Y-%m-%d") if member.joined_at else "—", inline=False)

    if warns:
        warn_text = "\n".join(f"• {w['reason']} — {w['moderator']} ({w['date']})" for w in warns[-5:])
        embed.add_field(name="Последние предупреждения", value=warn_text[:1024], inline=False)

    if puns:
        pun_text = "\n".join(f"• {p['text']} ({p['date']})" for p in puns[-5:])
        embed.add_field(name="История наказаний", value=pun_text[:1024], inline=False)

    return embed


# ================== КОМАНДЫ ==================
@tree.command(name="help", description="Список команд бота")
async def help_cmd(interaction: discord.Interaction):
    embed = discord.Embed(title="Infinity Yield Administration — Команды", color=discord.Color.gold())
    embed.add_field(name="/ban", value="Забанить пользователя", inline=False)
    embed.add_field(name="/kick", value="Кикнуть пользователя", inline=False)
    embed.add_field(name="/mute", value="Замутить пользователя (минуты)", inline=False)
    embed.add_field(name="/unmute", value="Снять мут", inline=False)
    embed.add_field(name="/warn", value="Выдать предупреждение", inline=False)
    embed.add_field(name="/unwarn", value="Снять последнее предупреждение", inline=False)
    embed.add_field(name="/clear", value="Очистить N сообщений", inline=False)
    embed.add_field(name="/profile", value="Профиль пользователя", inline=False)
    embed.add_field(name="/text", value="Отправить текст от имени бота", inline=False)
    embed.add_field(name="/panel", value="Информационная панель пользователя", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@tree.command(name="ban", description="Забанить пользователя")
@app_commands.describe(member="Пользователь", reason="Причина")
async def ban_cmd(interaction: discord.Interaction, member: discord.Member, reason: str = "Не указана"):
    if not can_ban(interaction.user):
        await interaction.response.send_message("Нет прав.", ephemeral=True); return
    try:
        await member.ban(reason=reason)
        log_punishment(member.id, f"Бан: {reason} ({interaction.user})")
        await interaction.response.send_message(f"{member.mention} забанен. Причина: {reason}")
    except Exception as e:
        await interaction.response.send_message(f"Ошибка: {e}", ephemeral=True)


@tree.command(name="kick", description="Кикнуть пользователя")
@app_commands.describe(member="Пользователь", reason="Причина")
async def kick_cmd(interaction: discord.Interaction, member: discord.Member, reason: str = "Не указана"):
    if not can_kick(interaction.user):
        await interaction.response.send_message("Нет прав.", ephemeral=True); return
    try:
        await member.kick(reason=reason)
        log_punishment(member.id, f"Кик: {reason} ({interaction.user})")
        await interaction.response.send_message(f"{member.mention} кикнут. Причина: {reason}")
    except Exception as e:
        await interaction.response.send_message(f"Ошибка: {e}", ephemeral=True)


@tree.command(name="mute", description="Замутить пользователя")
@app_commands.describe(member="Пользователь", minutes="Длительность в минутах", reason="Причина")
async def mute_cmd(interaction: discord.Interaction, member: discord.Member, minutes: int = 10, reason: str = "Не указана"):
    if not can_mute(interaction.user):
        await interaction.response.send_message("Нет прав.", ephemeral=True); return
    try:
        until = datetime.utcnow() + timedelta(minutes=minutes)
        await member.timeout(until, reason=reason)
        log_punishment(member.id, f"Мут {minutes} мин: {reason} ({interaction.user})")
        await interaction.response.send_message(f"{member.mention} замучен на {minutes} мин. Причина: {reason}")
    except Exception as e:
        await interaction.response.send_message(f"Ошибка: {e}", ephemeral=True)


@tree.command(name="unmute", description="Снять мут")
@app_commands.describe(member="Пользователь")
async def unmute_cmd(interaction: discord.Interaction, member: discord.Member):
    if not can_mute(interaction.user):
        await interaction.response.send_message("Нет прав.", ephemeral=True); return
    try:
        await member.timeout(None)
        await interaction.response.send_message(f"Мут с {member.mention} снят.")
    except Exception as e:
        await interaction.response.send_message(f"Ошибка: {e}", ephemeral=True)


@tree.command(name="warn", description="Выдать предупреждение")
@app_commands.describe(member="Пользователь", reason="Причина")
async def warn_cmd(interaction: discord.Interaction, member: discord.Member, reason: str = "Не указана"):
    if not can_warn(interaction.user):
        await interaction.response.send_message("Нет прав.", ephemeral=True); return
    uid = str(member.id)
    DATA["warns"].setdefault(uid, []).append({
        "reason": reason,
        "moderator": str(interaction.user),
        "date": datetime.utcnow().strftime("%Y-%m-%d %H:%M")
    })
    log_punishment(member.id, f"Предупреждение: {reason} ({interaction.user})")
    save_data(DATA)
    await interaction.response.send_message(f"{member.mention} получил предупреждение. Причина: {reason}")


@tree.command(name="unwarn", description="Снять последнее предупреждение")
@app_commands.describe(member="Пользователь")
async def unwarn_cmd(interaction: discord.Interaction, member: discord.Member):
    if not can_warn(interaction.user):
        await interaction.response.send_message("Нет прав.", ephemeral=True); return
    uid = str(member.id)
    if DATA["warns"].get(uid):
        DATA["warns"][uid].pop()
        save_data(DATA)
        await interaction.response.send_message(f"С {member.mention} снято последнее предупреждение.")
    else:
        await interaction.response.send_message("У пользователя нет предупреждений.", ephemeral=True)


@tree.command(name="clear", description="Очистить N сообщений в канале")
@app_commands.describe(amount="Количество сообщений (1-100)")
async def clear_cmd(interaction: discord.Interaction, amount: int):
    if not can_use_mod(interaction.user):
        await interaction.response.send_message("Нет прав.", ephemeral=True); return
    if amount < 1 or amount > 100:
        await interaction.response.send_message("Число от 1 до 100.", ephemeral=True); return
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.followup.send(f"Удалено сообщений: {len(deleted)}", ephemeral=True)


@tree.command(name="profile", description="Профиль пользователя")
@app_commands.describe(member="Пользователь")
async def profile_cmd(interaction: discord.Interaction, member: discord.Member = None):
    if not can_use_mod(interaction.user):
        await interaction.response.send_message("Нет прав.", ephemeral=True); return
    member = member or interaction.user
    embed = build_profile_embed(member)
    await interaction.response.send_message(embed=embed, view=ProfileView(member))


@tree.command(name="panel", description="Информационная панель пользователя")
@app_commands.describe(member="Пользователь")
async def panel_cmd(interaction: discord.Interaction, member: discord.Member = None):
    if not can_use_mod(interaction.user):
        await interaction.response.send_message("Нет прав.", ephemeral=True); return
    member = member or interaction.user
    embed = build_profile_embed(member)
    await interaction.response.send_message(embed=embed, view=ProfileView(member))


@tree.command(name="text", description="Отправить текст от имени бота")
async def text_cmd(interaction: discord.Interaction):
    if not can_text(interaction.user):
        await interaction.response.send_message("Нет прав.", ephemeral=True); return
    await interaction.response.send_modal(TextModal())


# ================== ЗАПУСК ==================
@bot.event
async def on_ready():
    await tree.sync()
    print(f"Бот запущен как {bot.user}")

    # Панель доната
    try:
        ch = bot.get_channel(DONATE_CHANNEL)
        if ch:
            async for msg in ch.history(limit=20):
                if msg.author == bot.user:
                    await msg.delete()
            embed = discord.Embed(
                title="Магазин привилегий — Infinity Yield",
                description=(
                    "Выберите подходящую привилегию и нажмите кнопку ниже.\n"
                    "После выбора свяжитесь с администрацией для оформления.\n\n"
                    "**Прайс-лист:**\n"
                    "• Модератор — 500₽\n"
                    "• Старший Модератор — 1000₽\n"
                    "• Главный Модератор — 1500₽\n"
                    "• Администратор — 2000₽\n"
                    "• Старший Администратор — 3000₽\n"
                    "• Главный Администратор — 4000₽"
                ),
                color=discord.Color.green()
            )
            await ch.send(embed=embed, view=DonateView())
    except Exception as e:
        print("Ошибка панели доната:", e)

    # Панель жалоб
    try:
        ch = bot.get_channel(COMPLAINT_CHANNEL)
        if ch:
            async for msg in ch.history(limit=20):
                if msg.author == bot.user:
                    await msg.delete()
            embed = discord.Embed(
                title="Подача жалоб",
                description=(
                    "Внимание! За неадекватное поведение при разборе жалобы, "
                    "а также за «шуточные» тикеты вы можете понести ответственность.\n\n"
                    "Нажмите кнопку ниже, чтобы подать жалобу."
                ),
                color=discord.Color.red()
            )
            await ch.send(embed=embed, view=ComplaintView())
    except Exception as e:
        print("Ошибка панели жалоб:", e)

    # Панель апелляций
    try:
        ch = bot.get_channel(APPEAL_CHANNEL)
        if ch:
            async for msg in ch.history(limit=20):
                if msg.author == bot.user:
                    await msg.delete()
            embed = discord.Embed(
                title="Подача апелляций",
                description=(
                    "Внимание! За неадекватное поведение при разборе апелляции, "
                    "а также за «шуточные» тикеты вы можете понести ответственность.\n\n"
                    "Нажмите кнопку ниже, чтобы подать апелляцию."
                ),
                color=discord.Color.orange()
            )
            await ch.send(embed=embed, view=AppealView())
    except Exception as e:
        print("Ошибка панели апелляций:", e)


bot.run(TOKEN)