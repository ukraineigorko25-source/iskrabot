import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import sqlite3
import os
import random
from datetime import timedelta
from aiohttp import web

DEVELOPER_ID = 824368499559497768

STAFF_ROLE_NAMES = [
    "Керівник діскорд",
    "Заступник керівника діскорд",
    "Діскорд майстер",
    "Спеціальний модератор діскорд",
    "Головний Модератор",
    "Заступник Головного Модератора",
    "Куратор Модерація",
    "Старший Модератор",
    "Модератор",
    "Молодший Модератор",
    "ГМ", "ЗГМ", "КМ", "СМ", "МД", "ММД",
    "🛡️ Модерація (Discord)",
    "Власник", "Керівник проєкту", "Спеціальний адміністратор",
    "Головний Адміністратор", "Заступник Головного Адміністратора", "ГА", "ЗГА"
]

COMPLAINT_TYPES = [
    "Скарги на модерацію",
    "Скарги на ГА",
    "Скарги на ЗГА",
    "Скарги на гравця",
    "Скарги на скам",
    "Скарги на медіа-партнерів",
    "Скарги на учасників Discord",
    "Скарги на адміністрацію",
    "Скарги на лідерів та заступників",
    "Скарги на сім'ї / клани"
]

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# ==================== БАЗА ДАНИХ (SQLite) ====================
db = sqlite3.connect("bot_database.db", check_same_thread=False)
cursor = db.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS guild_settings (
    guild_id INTEGER PRIMARY KEY,
    report_channel_id INTEGER
)""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS mod_stats (
    guild_id INTEGER,
    moderator_id INTEGER,
    closed_count INTEGER DEFAULT 0,
    total_rating INTEGER DEFAULT 0,
    rating_count INTEGER DEFAULT 0,
    PRIMARY KEY (guild_id, moderator_id)
)""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS warns (
    guild_id INTEGER,
    user_id INTEGER,
    warn_count INTEGER DEFAULT 0,
    PRIMARY KEY (guild_id, user_id)
)""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS user_nicknames (
    user_id INTEGER PRIMARY KEY,
    ingame_nick TEXT
)""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS complaint_counter (
    guild_id INTEGER PRIMARY KEY,
    counter INTEGER DEFAULT 0
)""")
db.commit()

def setup_database_migration():
    cursor.execute("PRAGMA table_info(mod_stats)")
    columns = [column[1] for column in cursor.fetchall()]
    if "total_rating" not in columns:
        try: cursor.execute("ALTER TABLE mod_stats ADD COLUMN total_rating INTEGER DEFAULT 0")
        except: pass
    if "rating_count" not in columns:
        try: cursor.execute("ALTER TABLE mod_stats ADD COLUMN rating_count INTEGER DEFAULT 0")
        except: pass
    db.commit()

setup_database_migration()

def get_next_complaint_id(guild_id: int) -> int:
    cursor.execute("SELECT counter FROM complaint_counter WHERE guild_id = ?", (guild_id,))
    row = cursor.fetchone()
    if row:
        new_id = row[0] + 1
        cursor.execute("UPDATE complaint_counter SET counter = ? WHERE guild_id = ?", (new_id, guild_id))
    else:
        new_id = 1
        cursor.execute("INSERT INTO complaint_counter (guild_id, counter) VALUES (?, 1)", (guild_id,))
    db.commit()
    return new_id

def add_mod_stat(guild_id: int, moderator_id: int, rating: int = 0):
    cursor.execute("SELECT closed_count, total_rating, rating_count FROM mod_stats WHERE guild_id = ? AND moderator_id = ?", (guild_id, moderator_id))
    row = cursor.fetchone()
    if row:
        closed = row[0] + 1
        t_rating = (row[1] or 0) + rating
        r_count = (row[2] or 0) + (1 if rating > 0 else 0)
        cursor.execute("""
        UPDATE mod_stats SET closed_count = ?, total_rating = ?, rating_count = ?
        WHERE guild_id = ? AND moderator_id = ?
        """, (closed, t_rating, r_count, guild_id, moderator_id))
    else:
        cursor.execute("""
        INSERT INTO mod_stats (guild_id, moderator_id, closed_count, total_rating, rating_count)
        VALUES (?, ?, 1, ?, ?)
        """, (closed, t_rating, 1 if rating > 0 else 0))
    db.commit()

def is_staff_or_admin(member: discord.Member) -> bool:
    if member.guild_permissions.administrator or member.guild_permissions.manage_guild:
        return True
    for role in member.roles:
        if role.name in STAFF_ROLE_NAMES:
            return True
    return False

# ==================== СИСТЕМА ЛОГУВАННЯ ====================

async def send_mod_log(guild: discord.Guild, text: str, color=discord.Color.red()):
    log_channel = None
    for channel in guild.text_channels:
        if any(name in channel.name.lower() for name in ["лог", "log", "покарання", "варн", "мод-лог"]):
            log_channel = channel
            break
    
    if not log_channel and guild.text_channels:
        log_channel = guild.text_channels[0]

    if log_channel:
        embed = discord.Embed(title="🛡️ Лог Сервера", description=text, color=color)
        embed.timestamp = discord.utils.utcnow()
        try:
            await log_channel.send(embed=embed)
        except Exception:
            pass

# ==================== ВЕБ-ПАНЕЛЬ (СПРОЩЕНА) ====================

async def web_index(request):
    return web.Response(text="<h1>IskraBot Online 24/7</h1>", content_type='text/html')

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', web_index)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

# ==================== ОСНОВНИЙ КЛАС БОТА ====================

class IskraBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        self.add_view(UniversalComplaintView())
        self.add_view(GenderSelectView())
        self.add_view(CallModControlView())
        self.add_view(ComplaintControlView())
        self.add_view(SquidGameView())
        
        try:
            synced = await self.tree.sync()
            print(f"✅ Синхронізовано команд: {len(synced)}")
        except Exception as e:
            print(f"❌ Помилка синхронізації: {e}")

bot = IskraBot()

@bot.event
async def on_ready():
    print(f"✅ Бот {bot.user} успішно запущений та готовий до роботи!")
    asyncio.create_task(start_web_server())

# ==================== ПРИВІТАННЯ ====================

@bot.event
async def on_member_join(member: discord.Member):
    welcome_channel = None
    for channel in member.guild.text_channels:
        if any(name in channel.name.lower() for name in ["вітання", "welcome", "загальний", "чат"]):
            welcome_channel = channel
            break
    
    if not welcome_channel and member.guild.text_channels:
        welcome_channel = member.guild.text_channels[0]

    if welcome_channel:
        embed = discord.Embed(
            title=f"👋 Вітаємо на сервері {member.guild.name}!",
            description=(
                f"Привіт, {member.mention}!\n\n"
                f"📌 Ознайомся з правилами сервера.\n"
                f"🎮 Бажаємо приємного спілкування та вдалої гри!"
            ),
            color=discord.Color.blurple()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        try: await welcome_channel.send(embed=embed)
        except Exception: pass

# ==================== ВСТАНОВЛЕННЯ НІКНЕЙМУ ====================

class SetNicknameModal(discord.ui.Modal):
    def __init__(self): super().__init__(title="Встановлення нікнейму")
    nick = discord.ui.TextInput(label="Вкажіть ваш ігровий нікнейм", placeholder="Taras_Shevchenko", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        cursor.execute("INSERT OR REPLACE INTO user_nicknames (user_id, ingame_nick) VALUES (?, ?)", (interaction.user.id, self.nick.value))
        db.commit()
        await interaction.response.send_message(f"✅ Ваш ігровий нікнейм збережено: **{self.nick.value}**.", ephemeral=True)

# ==================== УНІВЕРСАЛЬНА СИСТЕМА СКАРГ ====================

class AdminSelectDropdown(discord.ui.Select):
    def __init__(self, guild: discord.Guild):
        options = []
        staff_members = [m for m in guild.members if is_staff_or_admin(m) and not m.bot][:25]
        for member in staff_members:
            options.append(discord.SelectOption(label=member.display_name, value=str(member.id), description=f"@{member.name}"))
        if not options:
            options.append(discord.SelectOption(label="Немає доступних адмінів", value="0"))
        super().__init__(placeholder="Обрати відповідального адміністратора", min_values=1, max_values=1, options=options, custom_id="admin_select_dropdown")

    async def callback(self, interaction: discord.Interaction):
        if not is_staff_or_admin(interaction.user):
            return await interaction.response.send_message("❌ Недостатньо прав!", ephemeral=True)
        admin_id = int(self.values[0])
        admin_member = interaction.guild.get_member(admin_id)
        admin_name = admin_member.mention if admin_member else "Адміністратор"
        await interaction.response.send_message(f"👤 Відповідальним призначено: {admin_name}")

class ComplaintControlView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)

    @discord.ui.button(label="Взяти на розгляд", style=discord.ButtonStyle.primary, emoji="🔍", custom_id="take_c_v5")
    async def take(self, interaction: discord.Interaction, button):
        if not is_staff_or_admin(interaction.user): return await interaction.response.send_message("❌ Немає прав!", ephemeral=True)
        await interaction.response.defer()
        button.disabled = True
        await interaction.message.edit(view=self)
        await interaction.channel.send(f"🔍 Скаргу взяв на розгляд {interaction.user.mention}.")

    @discord.ui.button(label="Прийняти", style=discord.ButtonStyle.success, emoji="✅", custom_id="accept_c_v5")
    async def accept(self, interaction: discord.Interaction, button):
        if not is_staff_or_admin(interaction.user): return await interaction.response.send_message("❌ Немає прав!", ephemeral=True)
        add_mod_stat(interaction.guild.id, interaction.user.id)
        await interaction.response.send_message(f"✅ **Скаргу схвалено** адміністратором {interaction.user.mention}.")
        await send_mod_log(interaction.guild, f"✅ **СХВАЛЕНО СКАРГУ**\n👮 Адмін: {interaction.user.mention}\nКанал: {interaction.channel.mention}", discord.Color.green())

    @discord.ui.button(label="Відхилити", style=discord.ButtonStyle.danger, emoji="❌", custom_id="reject_c_v5")
    async def reject(self, interaction: discord.Interaction, button):
        if not is_staff_or_admin(interaction.user): return await interaction.response.send_message("❌ Немає прав!", ephemeral=True)
        add_mod_stat(interaction.guild.id, interaction.user.id)
        await interaction.response.send_message(f"❌ **Скаргу відхилено** адміністратором {interaction.user.mention}.")
        await send_mod_log(interaction.guild, f"❌ **ВІДХИЛЕНО СКАРГУ**\n👮 Адмін: {interaction.user.mention}\nКанал: {interaction.channel.mention}")

    @discord.ui.button(label="Вимкнути офтоп", style=discord.ButtonStyle.secondary, emoji="💬", custom_id="close_offtop_v5")
    async def close_offtop(self, interaction: discord.Interaction, button):
        if not is_staff_or_admin(interaction.user): return await interaction.response.send_message("❌ Немає прав!", ephemeral=True)
        await interaction.response.send_message("🔒 **Обговорення закрито.**")
        if isinstance(interaction.channel, discord.Thread):
            await interaction.channel.edit(locked=True)

class ForumComplaintModal(discord.ui.Modal):
    def __init__(self, category_name: str, ingame_nick: str):
        super().__init__(title=f"Подача скарги: {category_name[:18]}")
        self.category_name = category_name
        self.ingame_nick = ingame_nick

    target = discord.ui.TextInput(label="Нік / Discord порушника", placeholder="Igor_Storm / @user", required=True)
    reason = discord.ui.TextInput(label="Причина скарги", placeholder="DM, Скам, Образи тощо", required=True)
    essence = discord.ui.TextInput(label="Опис ситуації", style=discord.TextStyle.paragraph, placeholder="Детально розпишіть суть...", required=True)
    date_p = discord.ui.TextInput(label="Дата порушення", placeholder="19.10.2026", required=True)
    proofs = discord.ui.TextInput(label="Докази (посилання)", style=discord.TextStyle.paragraph, placeholder="Imgur / YouTube посилання", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        c_id = get_next_complaint_id(guild.id)
        thread_name = f"#{c_id} | {self.target.value} | {self.reason.value}"

        embed = discord.Embed(title=f"📋 {self.category_name} No{c_id}", color=discord.Color.dark_theme())
        embed.description = (
            f"**Автор скарги:** {self.ingame_nick} ({interaction.user.mention})\n"
            f"**Порушник:** {self.target.value}\n"
            f"**Причина:** {self.reason.value}\n"
            f"**Суть:** {self.essence.value}\n"
            f"**Дата:** {self.date_p.value}\n"
            f"**Докази:** {self.proofs.value}"
        )
        embed.set_footer(text=f"Подано: {discord.utils.utcnow().strftime('%d.%m.%Y, %H:%M:%S')}")

        view = ComplaintControlView()
        view.add_item(AdminSelectDropdown(guild))

        if isinstance(interaction.channel, discord.ForumChannel):
            thread = await interaction.channel.create_thread(name=thread_name, embed=embed, view=view)
            await interaction.followup.send(f"✅ Скаргу створено -> {thread.thread.mention}", ephemeral=True)
        else:
            await interaction.channel.send(embed=embed, view=view)
            await interaction.followup.send("✅ Скаргу успішно надіслано!", ephemeral=True)

class ComplaintCategorySelect(discord.ui.Select):
    def __init__(self):
        options = [discord.SelectOption(label=c, value=c) for c in COMPLAINT_TYPES]
        super().__init__(placeholder="Оберіть категорію скарги...", min_values=1, max_values=1, options=options, custom_id="complaint_cat_select")

    async def callback(self, interaction: discord.Interaction):
        cursor.execute("SELECT ingame_nick FROM user_nicknames WHERE user_id = ?", (interaction.user.id,))
        row = cursor.fetchone()
        if not row:
            return await interaction.response.send_message("❌ Спочатку вкажіть ваш ігровий нікнейм кнопкою **'Вказати нікнейм'**!", ephemeral=True)
        
        selected_category = self.values[0]
        await interaction.response.send_modal(ForumComplaintModal(selected_category, row[0]))

class UniversalComplaintView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ComplaintCategorySelect())

    @discord.ui.button(label="Вказати нікнейм", style=discord.ButtonStyle.secondary, emoji="✏️", custom_id="universal_nick_btn")
    async def open_nick(self, interaction: discord.Interaction, button):
        await interaction.response.send_modal(SetNicknameModal())

# ==================== ІНШІ ПАНЕЛІ ТА ІГРИ ====================

class SquidGameView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="🦑 Почати 'Ігру в кальмара'", style=discord.ButtonStyle.danger, emoji="🎮", custom_id="start_squid_game_main")
    async def start(self, interaction: discord.Interaction, b):
        embed = discord.Embed(title="🦑 Гра розпочата!", description="Учасники проходять раунд «Тихіше їдеш — далі будеш»...", color=discord.Color.red())
        await interaction.response.send_message(embed=embed)

class GenderSelectView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Хлопець", style=discord.ButtonStyle.primary, emoji="👦", custom_id="role_boy_btn_v3")
    async def boy(self, interaction: discord.Interaction, b):
        role = discord.utils.get(interaction.guild.roles, name="Хлопець")
        if role:
            if role in interaction.user.roles: await interaction.user.remove_roles(role)
            else: await interaction.user.add_roles(role)
            await interaction.response.send_message("✅ Роль оновлено!", ephemeral=True)

    @discord.ui.button(label="Дівчина", style=discord.ButtonStyle.success, emoji="👧", custom_id="role_girl_btn_v3")
    async def girl(self, interaction: discord.Interaction, b):
        role = discord.utils.get(interaction.guild.roles, name="Дівчина")
        if role:
            if role in interaction.user.roles: await interaction.user.remove_roles(role)
            else: await interaction.user.add_roles(role)
            await interaction.response.send_message("✅ Роль оновлено!", ephemeral=True)

class CallModControlView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Взяти виклик", style=discord.ButtonStyle.primary, emoji="🛡️", custom_id="callmod_take_btn_v3")
    async def take(self, interaction: discord.Interaction, button):
        if not is_staff_or_admin(interaction.user): return await interaction.response.send_message("❌ Немає прав!", ephemeral=True)
        await interaction.response.defer()
        button.disabled = True
        await interaction.message.edit(view=self)
        await interaction.channel.send(f"🛡️ {interaction.user.mention} прийняв виклик.")

# ==================== СЛЕШ-КОМАНДИ ====================

@bot.tree.command(name="setup_complaint_panel", description="Створити панель скарг")
@app_commands.default_permissions(administrator=True)
async def setup_complaint_panel(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📋 Подача скарги",
        description="Оберіть категорію з меню нижче або вкажіть ваш нікнейм.",
        color=discord.Color.red()
    )
    await interaction.channel.send(embed=embed, view=UniversalComplaintView())
    await interaction.response.send_message("✅ Панель створено!", ephemeral=True)

@bot.tree.command(name="squidgame", description="Запустити мінігру «Ігра в кальмара»")
@app_commands.default_permissions(manage_messages=True)
async def squidgame_cmd(interaction: discord.Interaction):
    await interaction.channel.send(embed=discord.Embed(title="🦑 Гра в кальмара", color=discord.Color.red()), view=SquidGameView())
    await interaction.response.send_message("✅ Створено!", ephemeral=True)

bot.run(os.getenv('TOKEN'))
