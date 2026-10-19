import discord
from discord import app_commands
from discord.ext import commands
import re
import asyncio
import sqlite3
import io
import os
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
    "Власник", "Керівник проєкту", "Спеціальний адміністратор"
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

# --- АВТО-МИГРАЦИЯ БАЗЫ ДАННЫХ ---
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
        """, (guild_id, moderator_id, rating, 1 if rating > 0 else 0))
    db.commit()

def is_staff_or_admin(member: discord.Member) -> bool:
    if member.guild_permissions.administrator or member.guild_permissions.manage_guild:
        return True
    for role in member.roles:
        if role.name in STAFF_ROLE_NAMES:
            return True
    return False

# ==================== ВЕБ-ПАНЕЛЬ ====================

async def web_index(request):
    guilds_count = len(bot.guilds)
    total_members = sum(g.member_count for g in bot.guilds)
    cursor.execute("SELECT SUM(closed_count) FROM mod_stats")
    res = cursor.fetchone()
    total_closed = res[0] if res and res[0] else 0

    html_content = f"""
    <!DOCTYPE html>
    <html lang="uk">
    <head>
        <meta charset="UTF-8">
        <title>IskraBot | Панель Власника</title>
        <style>
            body {{ background-color: #0d1117; color: #c9d1d9; font-family: sans-serif; padding: 40px; margin: 0; }}
            .container {{ max-width: 900px; margin: 0 auto; background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 30px; }}
            h1 {{ color: #58a6ff; margin-top: 0; }}
            .status {{ display: inline-block; background: #238636; color: white; padding: 5px 12px; border-radius: 20px; font-size: 14px; font-weight: bold; margin-bottom: 20px; }}
            .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 20px; margin-top: 25px; }}
            .card {{ background: #21262d; border: 1px solid #30363d; border-radius: 8px; padding: 20px; text-align: center; }}
            .card p {{ font-size: 28px; font-weight: bold; color: #f0f6fc; margin: 0; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>⚡ Панель керування IskraBot</h1>
            <div class="status">🟢 Бот активний 24/7</div>
            <div class="stats-grid">
                <div class="card"><h3>СЕРВЕРИ</h3><p>{guilds_count}</p></div>
                <div class="card"><h3>КОРИСТУВАЧІВ</h3><p>{total_members}</p></div>
                <div class="card"><h3>ЗАКРИТИХ ТІКЕТІВ</h3><p>{total_closed}</p></div>
            </div>
        </div>
    </body>
    </html>
    """
    return web.Response(text=html_content, content_type='text/html')

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', web_index)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

class IskraBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        self.add_view(ModernTicketView())
        self.add_view(CreateComplaintView("Скарги на гравців"))
        self.add_view(GenderSelectView())
        self.add_view(CallModControlView())
        self.add_view(FactionPanelView())
        self.add_view(PlayerAppPanelView())
        self.add_view(ComplaintControlView())
        
        try:
            synced = await self.tree.sync()
            print(f"✅ Синхронізовано команд: {len(synced)}")
        except Exception as e:
            print(f"❌ Помилка: {e}")

bot = IskraBot()

@bot.event
async def on_ready():
    print(f"Бот {bot.user} успішно запущений!")
    asyncio.create_task(start_web_server())

# ==================== ФОРМА ВСТАНОВЛЕННЯ НІКНЕЙМУ ====================

class SetNicknameModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="Встановлення нікнейму")

    nick = discord.ui.TextInput(label="Вкажіть ваш ігровий нікнейм", placeholder="Приклад: Taras_Shevchenko", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        cursor.execute("INSERT OR REPLACE INTO user_nicknames (user_id, ingame_nick) VALUES (?, ?)", (interaction.user.id, self.nick.value))
        db.commit()
        await interaction.response.send_message(f"✅ Ваш ігровий нікнейм успішно встановлено на **{self.nick.value}**.", ephemeral=True)

# ==================== СИСТЕМА СКАРГ ТА ФОРУМІВ (ЯК НА ВІДЕО) ====================

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
        await interaction.response.send_message(f"👤 Відповідальним адміністратором призначено: {admin_name}")

class ComplaintControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Взяти на розгляд", style=discord.ButtonStyle.primary, emoji="🔍", custom_id="take_c_v5")
    async def take_complaint(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff_or_admin(interaction.user):
            return await interaction.response.send_message("❌ Недостатньо прав!", ephemeral=True)
        await interaction.response.defer()
        button.disabled = True
        await interaction.message.edit(view=self)
        await interaction.channel.send(f"🔍 Скаргу взяв на розгляд адміністратор {interaction.user.mention}.")

    @discord.ui.button(label="Прийняти", style=discord.ButtonStyle.success, emoji="✅", custom_id="accept_c_v5")
    async def accept_complaint(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff_or_admin(interaction.user):
            return await interaction.response.send_message("❌ Недостатньо прав!", ephemeral=True)
        add_mod_stat(interaction.guild.id, interaction.user.id)
        await interaction.response.send_message(f"✅ **Скаргу було схвалено** адміністратором {interaction.user.mention}.")

    @discord.ui.button(label="Відхилити", style=discord.ButtonStyle.danger, emoji="❌", custom_id="reject_c_v5")
    async def reject_complaint(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff_or_admin(interaction.user):
            return await interaction.response.send_message("❌ Недостатньо прав!", ephemeral=True)
        add_mod_stat(interaction.guild.id, interaction.user.id)
        await interaction.response.send_message(f"❌ **Скаргу було відхилено** адміністратором {interaction.user.mention}.")

    @discord.ui.button(label="Вимкнути офтоп", style=discord.ButtonStyle.secondary, emoji="💬", custom_id="close_offtop_v5")
    async def close_offtop(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff_or_admin(interaction.user):
            return await interaction.response.send_message("❌ Недостатньо прав!", ephemeral=True)
        await interaction.response.send_message("🔒 **Обговорення закрито.** Допис переведено в режим читання.")
        if isinstance(interaction.channel, discord.Thread):
            await interaction.channel.edit(locked=True)

class ForumComplaintModal(discord.ui.Modal):
    def __init__(self, category_name: str, ingame_nick: str):
        super().__init__(title=f"Скарги на гравців ({category_name})")
        self.category_name = category_name
        self.ingame_nick = ingame_nick

    reason = discord.ui.TextInput(label="Причина скарги", placeholder="Приклад: DM, MG, PG, Образи тощо", required=True)
    target_discord = discord.ui.TextInput(label="Вкажіть Discord гравця", placeholder="Приклад: 2tired", required=True)
    essence = discord.ui.TextInput(label="Опис скарги", style=discord.TextStyle.paragraph, placeholder="Приклад: Flood", required=True)
    date_p = discord.ui.TextInput(label="Дата порушення", placeholder="Приклад: 19.10.2026, 20:44", required=True)
    proofs = discord.ui.TextInput(label="Докази", style=discord.TextStyle.paragraph, placeholder="Посилання на скріноти/відео", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild

        c_id = get_next_complaint_id(guild.id)
        thread_name = f"#{c_id} | {self.target_discord.value} | {self.reason.value}"

        embed = discord.Embed(
            title=f"Скарга на гравця ({self.category_name}) No{c_id}",
            color=discord.Color.dark_theme()
        )
        embed.description = (
            f"**Нікнейм автора:** {self.ingame_nick} ({interaction.user.mention})\n"
            f"**Discord гравця:** {self.target_discord.value}\n"
            f"**Суть скарги:** {self.essence.value}\n"
            f"**Дата порушення:** {self.date_p.value}\n"
            f"**Докази:** {self.proofs.value}"
        )
        embed.set_footer(text=f"Дата подачі: {discord.utils.utcnow().strftime('%d.%m.%Y, %H:%M:%S')}")

        view = ComplaintControlView()
        view.add_item(AdminSelectDropdown(guild))

        # Перевірка чи канал є Форумом
        if isinstance(interaction.channel, discord.ForumChannel):
            thread_with_msg = await interaction.channel.create_thread(
                name=thread_name,
                embed=embed,
                view=view
            )
            await interaction.followup.send(f"✅ Вашу скаргу було успішно створено. Перейдіть -> {thread_with_msg.thread.mention}", ephemeral=True)
        else:
            msg = await interaction.channel.send(embed=embed, view=view)
            await interaction.followup.send(f"✅ Скаргу надіслано в канал {interaction.channel.mention}", ephemeral=True)

class CreateComplaintView(discord.ui.View):
    def __init__(self, category_name: str = "Discord"):
        super().__init__(timeout=None)
        self.category_name = category_name

    @discord.ui.button(label="Подати скаргу", style=discord.ButtonStyle.primary, emoji="📝", custom_id="open_c_main_btn")
    async def open_complaint_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        cursor.execute("SELECT ingame_nick FROM user_nicknames WHERE user_id = ?", (interaction.user.id,))
        row = cursor.fetchone()
        
        if not row:
            return await interaction.response.send_message(
                "❌ **Помилка:** Ви повинні вказати ваш ігровий нікнейм перед подачею скарги. Скористайтеся кнопкою **\"Вказати нікнейм\"**.",
                ephemeral=True
            )

        await interaction.response.send_modal(ForumComplaintModal(self.category_name, row[0]))

    @discord.ui.button(label="Вказати нікнейм", style=discord.ButtonStyle.secondary, emoji="✏️", custom_id="set_nick_main_btn")
    async def open_set_nick_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SetNicknameModal())

# ==================== РЕШТА ПАНЕЛЕЙ ТА КОМАНД ====================

@bot.tree.command(name="setup_forum_complaints", description="Створити форму та форум для скарг як на відео")
@app_commands.default_permissions(administrator=True)
async def setup_forum_complaints(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild
    category = await guild.create_category("📋 Скарги на гравців")
    forum_channel = await guild.create_forum_channel("скарги-на-гравців-discord", category=category)
    
    embed = discord.Embed(
        title="💬 Скарги на гравців Discord",
        description="У цьому каналі ви можете створити скаргу на учасників. Щоб створити скаргу, натисніть на кнопку нижче.",
        color=discord.Color.red()
    )
    await forum_channel.send(embed=embed, view=CreateComplaintView("Discord"))
    await interaction.followup.send(f"✅ Форум скарг створено -> {forum_channel.mention}", ephemeral=True)

# Запуск бота через зміну середовища
bot.run(os.getenv('TOKEN'))
