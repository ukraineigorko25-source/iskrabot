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
    "🛡️ Модерація (Discord)"
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
db.commit()

# --- АВТО-МИГРАЦИЯ БАЗЫ ДАННЫХ ДЛЯ СТАРОГО СЕРВЕРА ---
def setup_database_migration():
    cursor.execute("PRAGMA table_info(mod_stats)")
    columns = [column[1] for column in cursor.fetchall()]
    
    if "total_rating" not in columns:
        try:
            cursor.execute("ALTER TABLE mod_stats ADD COLUMN total_rating INTEGER DEFAULT 0")
        except Exception:
            pass
            
    if "rating_count" not in columns:
        try:
            cursor.execute("ALTER TABLE mod_stats ADD COLUMN rating_count INTEGER DEFAULT 0")
        except Exception:
            pass
            
    db.commit()

setup_database_migration()

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

async def send_mod_log(guild: discord.Guild, text: str, color=discord.Color.red()):
    log_channel = None
    for channel in guild.text_channels:
        if "покарання" in channel.name.lower() or "карань" in channel.name.lower():
            log_channel = channel
            break
    
    if not log_channel:
        for channel in guild.text_channels:
            if any(name in channel.name.lower() for name in ["логи", "log", "варни"]):
                log_channel = channel
                break

    if log_channel:
        embed = discord.Embed(description=text, color=color)
        embed.timestamp = discord.utils.utcnow()
        try:
            await log_channel.send(embed=embed)
        except Exception:
            pass

class IskraBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        self.add_view(ModernTicketView())
        self.add_view(ComplaintControlView())
        self.add_view(CreateComplaintView("Скарги на гравців"))
        self.add_view(GenderSelectView())
        self.add_view(CallModControlView())
        self.add_view(FactionPanelView())
        self.add_view(PlayerAppPanelView())
        
        try:
            synced = await self.tree.sync()
            print(f"✅ Успішно синхронізовано глобальних команд: {len(synced)}")
        except Exception as e:
            print(f"❌ Помилка синхронізації: {e}")

bot = IskraBot()

def is_staff_or_admin(member: discord.Member) -> bool:
    if member.guild_permissions.administrator or member.guild_permissions.manage_guild:
        return True
    for role in member.roles:
        if role.name in STAFF_ROLE_NAMES:
            return True
    return False

# ==================== ВЕБ-ПАНЕЛЬ (AIOHTTP) ====================

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
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>IskraBot | Панель Власника</title>
        <style>
            body {{ background-color: #0d1117; color: #c9d1d9; font-family: sans-serif; padding: 40px; margin: 0; }}
            .container {{ max-width: 900px; margin: 0 auto; background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 30px; box-shadow: 0 4px 20px rgba(0,0,0,0.5); }}
            h1 {{ color: #58a6ff; margin-top: 0; }}
            .status {{ display: inline-block; background: #238636; color: white; padding: 5px 12px; border-radius: 20px; font-size: 14px; font-weight: bold; margin-bottom: 20px; }}
            .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 20px; margin-top: 25px; }}
            .card {{ background: #21262d; border: 1px solid #30363d; border-radius: 8px; padding: 20px; text-align: center; }}
            .card h3 {{ color: #8b949e; font-size: 14px; margin-bottom: 10px; }}
            .card p {{ font-size: 28px; font-weight: bold; color: #f0f6fc; margin: 0; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>⚡ Панель керування IskraBot</h1>
            <div class="status">🟢 Бот активний 24/7</div>
            <p>Публічна веб-панель хостингу працює коректно.</p>
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
    print(f"🌐 Веб-панель успішно запущена на порту {port}")

@bot.event
async def on_ready():
    print(f"Бот {bot.user} успішно запущений!")
    asyncio.create_task(start_web_server())

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        await bot.process_commands(message)
        return

    if isinstance(message.author, discord.Member) and is_staff_or_admin(message.author):
        await bot.process_commands(message)
        return

    if message.channel.name.startswith("🎫-") or message.channel.name.startswith("фракція-"):
        await bot.process_commands(message)
        return

    url_pattern = re.compile(r'(https?://\S+|www\.\S+|discord\.gg/\S+|discord\.com/invite/\S+)', re.IGNORECASE)
    if url_pattern.search(message.content):
        try:
            await message.delete()
            await message.guild.ban(message.author, reason="Авто-бан: посилання (спам)")
        except Exception:
            pass

    await bot.process_commands(message)

# ==================== СЛЕШ-КОМАНДИ ====================

@bot.tree.command(name="sync", description="Оновити глобальні команди")
@app_commands.default_permissions(administrator=True)
async def sync_command(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    try:
        synced = await bot.tree.sync()
        await interaction.followup.send(f"✅ Успішно! Синхронізовано команд: {len(synced)}", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Помилка: {e}", ephemeral=True)

@bot.tree.command(name="dev_giverole", description="[Тільки для засновника] Видати собі роль (без логів)")
async def dev_giverole(interaction: discord.Interaction, role: discord.Role):
    if interaction.user.id != DEVELOPER_ID:
        await interaction.response.send_message("❌ Доступно лише засновнику бота!", ephemeral=True)
        return
    try:
        await interaction.user.add_roles(role, reason="Спеціальна команда засновника")
        await interaction.response.send_message(f"👑 Видано роль **{role.name}**!", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Помилка: {e}", ephemeral=True)

@bot.tree.command(name="dev_removerole", description="[Тільки для засновника] Зняти з себе роль (без логів)")
async def dev_removerole(interaction: discord.Interaction, role: discord.Role):
    if interaction.user.id != DEVELOPER_ID:
        await interaction.response.send_message("❌ Доступно лише засновнику бота!", ephemeral=True)
        return
    try:
        await interaction.user.remove_roles(role, reason="Спеціальна команда засновника")
        await interaction.response.send_message(f"👑 Знято роль **{role.name}**!", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Помилка: {e}", ephemeral=True)

@bot.tree.command(name="say", description="Написати повідомлення від імені бота")
@app_commands.default_permissions(manage_messages=True)
async def say_command(interaction: discord.Interaction, message: str):
    if not is_staff_or_admin(interaction.user):
        await interaction.response.send_message("❌ Немає прав!", ephemeral=True)
        return
    await interaction.channel.send(message)
    await interaction.response.send_message("✅ Повідомлення надіслано!", ephemeral=True)

@bot.tree.command(name="setup_system", description="Створити категорію та форум для скарг")
@app_commands.default_permissions(administrator=True)
async def setup_system(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild
    category = await guild.create_category("📋 Скарги та Підтримка")
    forum_channel = await guild.create_forum_channel("скарги-на-гравців", category=category)
    embed = discord.Embed(title="📋 ФОРМА ПОДАЧІ — СКАРГИ НА ГРАВЦІВ", color=discord.Color.red())
    await forum_channel.send(embed=embed, view=CreateComplaintView("Скарги на гравців"))
    await interaction.followup.send(f"✅ Створено форум {forum_channel.mention}!", ephemeral=True)

@bot.tree.command(name="ticketpanel", description="Створити панель тікетів для звернення до модерації")
@app_commands.default_permissions(administrator=True)
async def ticketpanel(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🛡️ Звернення до Модерації Discord",
        description="Потрібна допомога чи є запитання? Натисніть кнопку нижче, щоб відкрити приватний тікет із модерацією.",
        color=discord.Color.blurple()
    )
    await interaction.channel.send(embed=embed, view=ModernTicketView())
    await interaction.response.send_message("✅ Панель тікетів створена!", ephemeral=True)

@bot.tree.command(name="playerpanel", description="Створити панель заявки на роль гравця")
@app_commands.default_permissions(administrator=True)
async def playerpanel(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🎮 Отримання ролі Гравець",
        description="Натисніть кнопку нижче, щоб подати заявку на отримання ролі гравця (розглядає модерація).",
        color=discord.Color.blue()
    )
    await interaction.channel.send(embed=embed, view=PlayerAppPanelView())
    await interaction.response.send_message("✅ Панель ролі гравця створена!", ephemeral=True)

@bot.tree.command(name="factionpanel", description="Створити панель подачі заявки на фракційну роль")
@app_commands.default_permissions(administrator=True)
async def factionpanel(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🏛️ Отримання ролі в організації",
        description="Щоб подати заявку на отримання ролі в одній із фракцій — ознайомтеся з інструкцією та натисніть кнопку **«Подати заявку»**.",
        color=discord.Color.gold()
    )
    await interaction.channel.send(embed=embed, view=FactionPanelView())
    await interaction.response.send_message("✅ Панель фракцій створена!", ephemeral=True)

@bot.tree.command(name="genderpanel", description="Створити панель вибору ролі (хлопець / дівчина)")
@app_commands.default_permissions(administrator=True)
async def genderpanel(interaction: discord.Interaction):
    embed = discord.Embed(title="🎭 Вибір ролі (Стать)", description="Натисніть кнопку, щоб отримати роль:", color=discord.Color.magenta())
    await interaction.channel.send(embed=embed, view=GenderSelectView())
    await interaction.response.send_message("✅ Панель ролей створена!", ephemeral=True)

@bot.tree.command(name="modstats", description="Переглянути рейтинг та статистику роботи модераторів")
@app_commands.default_permissions(manage_messages=True)
async def modstats(interaction: discord.Interaction):
    cursor.execute("SELECT moderator_id, closed_count, total_rating, rating_count FROM mod_stats WHERE guild_id = ? ORDER BY closed_count DESC", (interaction.guild.id,))
    rows = cursor.fetchall()
    
    embed = discord.Embed(title="🏆 Рейтинг та Статистика модераторів", color=discord.Color.gold())
    if not rows:
        embed.description = "Статистика поки порожня."
    else:
        for idx, (m_id, closed, t_rating, r_count) in enumerate(rows, 1):
            user = interaction.guild.get_member(m_id)
            name = user.display_name if user else f"ID: {m_id}"
            avg_rating = round((t_rating or 0) / (r_count or 1), 1) if r_count else 0.0
            embed.add_field(
                name=f"#{idx} | {name}",
                value=f"📌 Закрито тікетів/скарг: **{closed}**\n⭐ Середня оцінка: **{avg_rating} / 5.0**",
                inline=False
            )
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="ban", description="Заблокувати користувача на сервері")
@app_commands.default_permissions(ban_members=True)
async def ban_member(interaction: discord.Interaction, member: discord.Member, reason: str = "Причина не вказана"):
    if not is_staff_or_admin(interaction.user):
        await interaction.response.send_message("❌ Немає прав!", ephemeral=True)
        return
    try:
        await member.send(f"🔨 Вас було **заблоковано** на сервері **{interaction.guild.name}**.\n📝 **Причина:** {reason}")
    except Exception:
        pass

    await member.ban(reason=reason)
    add_mod_stat(interaction.guild.id, interaction.user.id)
    await interaction.response.send_message(f"🔨 Заблоковано {member.mention}. Причина: {reason}")
    await send_mod_log(interaction.guild, f"🔨 Модератор {interaction.user.mention} заблокував гравця {member.mention}.\n📝 **Причина:** {reason}")

@bot.tree.command(name="unban", description="Зняти бан з користувача за його ID")
@app_commands.default_permissions(ban_members=True)
async def unban_member(interaction: discord.Interaction, user_id: str, reason: str = "Причина не вказана"):
    if not is_staff_or_admin(interaction.user):
        await interaction.response.send_message("❌ Немає прав!", ephemeral=True)
        return
    try:
        user = await bot.fetch_user(int(user_id))
        await interaction.guild.unban(user, reason=reason)
        await interaction.response.send_message(f"🔓 Знято бан з користувача {user.mention}.")
        await send_mod_log(interaction.guild, f"🔓 Модератор {interaction.user.mention} зняв бан з гравця {user.mention}.\n📝 **Причина:** {reason}", discord.Color.green())
    except Exception as e:
        await interaction.response.send_message(f"❌ Помилка: {e}", ephemeral=True)

@bot.tree.command(name="kick", description="Вигнати користувача з сервера")
@app_commands.default_permissions(kick_members=True)
async def kick_member(interaction: discord.Interaction, member: discord.Member, reason: str = "Причина не вказана"):
    if not is_staff_or_admin(interaction.user):
        await interaction.response.send_message("❌ Немає прав!", ephemeral=True)
        return
    try:
        await member.send(f"👢 Вас було **вигнано** з сервера **{interaction.guild.name}**.\n📝 **Причина:** {reason}")
    except Exception:
        pass

    await member.kick(reason=reason)
    add_mod_stat(interaction.guild.id, interaction.user.id)
    await interaction.response.send_message(f"👢 Вигнано {member.mention}. Причина: {reason}")
    await send_mod_log(interaction.guild, f"👢 Модератор {interaction.user.mention} вигнав гравця {member.mention}.\n📝 **Причина:** {reason}")

@bot.tree.command(name="mute", description="Замутити користувача на певний час (у хвилинах)")
@app_commands.default_permissions(moderate_members=True)
async def mute_member(interaction: discord.Interaction, member: discord.Member, minutes: int, reason: str = "Причина не вказана"):
    if not is_staff_or_admin(interaction.user):
        await interaction.response.send_message("❌ Немає прав!", ephemeral=True)
        return
    try:
        duration = timedelta(minutes=minutes)
        await member.timeout(duration, reason=reason)
        try:
            await member.send(f"🔇 Вам було видано **мут** на сервері **{interaction.guild.name}** на **{minutes} хв**.\n📝 **Причина:** {reason}")
        except Exception:
            pass

        add_mod_stat(interaction.guild.id, interaction.user.id)
        await interaction.response.send_message(f"🔇 Користувача {member.mention} замучено на {minutes} хв.")
        await send_mod_log(interaction.guild, f"🔨 Модератор {interaction.user.mention} замутив гравця {member.mention} на **{minutes} хв**.\n📝 **Причина:** {reason}")
    except Exception as e:
        await interaction.response.send_message(f"❌ Помилка муту: {e}", ephemeral=True)

@bot.tree.command(name="unmute", description="Зняти мут з користувача")
@app_commands.default_permissions(moderate_members=True)
async def unmute_member(interaction: discord.Interaction, member: discord.Member, reason: str = "Причина не вказана"):
    if not is_staff_or_admin(interaction.user):
        await interaction.response.send_message("❌ Немає прав!", ephemeral=True)
        return
    try:
        await member.timeout(None, reason=reason)
        try:
            await member.send(f"🔊 З вас було **знято мут** на сервері **{interaction.guild.name}**.")
        except Exception:
            pass

        await interaction.response.send_message(f"🔊 Знято мут з {member.mention}.")
        await send_mod_log(interaction.guild, f"🔊 Модератор {interaction.user.mention} зняв мут з гравця {member.mention}.\n📝 **Причина:** {reason}", discord.Color.green())
    except Exception as e:
        await interaction.response.send_message(f"❌ Помилка: {e}", ephemeral=True)

@bot.tree.command(name="warn", description="Видати попередження (варн) користувачу")
@app_commands.default_permissions(moderate_members=True)
async def warn_member(interaction: discord.Interaction, member: discord.Member, reason: str = "Причина не вказана"):
    if not is_staff_or_admin(interaction.user):
        await interaction.response.send_message("❌ Немає прав!", ephemeral=True)
        return
    
    cursor.execute("""
    INSERT INTO warns (guild_id, user_id, warn_count)
    VALUES (?, ?, 1)
    ON CONFLICT(guild_id, user_id) DO UPDATE SET
        warn_count = warn_count + 1
    """, (interaction.guild.id, member.id))
    db.commit()

    cursor.execute("SELECT warn_count FROM warns WHERE guild_id = ? AND user_id = ?", (interaction.guild.id, member.id))
    total_warns = cursor.fetchone()[0]

    try:
        await member.send(f"⚠️ Вам було видано **попередження (варн)** на сервері **{interaction.guild.name}** [{total_warns}/3].\n📝 **Причина:** {reason}")
    except Exception:
        pass

    add_mod_stat(interaction.guild.id, interaction.user.id)
    await interaction.response.send_message(f"⚠️ Користувач {member.mention} отримав варн. Всього: {total_warns}")
    await send_mod_log(interaction.guild, f"⚠️ Модератор {interaction.user.mention} видав варн гравцю {member.mention} **[{total_warns}/3]**.\n📝 **Причина:** {reason}", discord.Color.orange())

@bot.tree.command(name="unwarn", description="Зняти попередження з користувача")
@app_commands.default_permissions(moderate_members=True)
async def unwarn_member(interaction: discord.Interaction, member: discord.Member):
    if not is_staff_or_admin(interaction.user):
        await interaction.response.send_message("❌ Немає прав!", ephemeral=True)
        return
    
    cursor.execute("SELECT warn_count FROM warns WHERE guild_id = ? AND user_id = ?", (interaction.guild.id, member.id))
    res = cursor.fetchone()
    if not res or res[0] <= 0:
        await interaction.response.send_message(f"❌ У користувача немає активних варнів.", ephemeral=True)
        return

    cursor.execute("UPDATE warns SET warn_count = warn_count - 1 WHERE guild_id = ? AND user_id = ?", (interaction.guild.id, member.id))
    db.commit()
    
    cursor.execute("SELECT warn_count FROM warns WHERE guild_id = ? AND user_id = ?", (interaction.guild.id, member.id))
    new_count = cursor.fetchone()[0]

    try:
        await member.send(f"✅ З вас було **знято 1 попередження** на сервері **{interaction.guild.name}**. Залишилось: {new_count}")
    except Exception:
        pass

    await interaction.response.send_message(f"✅ Знято 1 варн з {member.mention}. Залишилось: {new_count}")

@bot.tree.command(name="clear", description="Очистити повідомлення в чаті")
@app_commands.default_permissions(manage_messages=True)
async def clear_messages(interaction: discord.Interaction, amount: int):
    if not is_staff_or_admin(interaction.user):
        await interaction.response.send_message("❌ Немає прав!", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.followup.send(f"🧹 Видалено {len(deleted)} повідомлень.", ephemeral=True)

@bot.tree.command(name="callmod", description="Викликати модерацію")
async def callmod(interaction: discord.Interaction, description: str):
    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild
    mod_role = discord.utils.get(guild.roles, name="🛡️ Модерація (Discord)") or discord.utils.get(guild.roles, name="Модератор")
    role_mention = mod_role.mention if mod_role else "@Модерація"

    embed = discord.Embed(
        title="🚨 ЕКСТРЕНИЙ ВИКЛИК МОДЕРАЦІЇ",
        description=f"**Ситуація:** {description}\n**Викликав:** {interaction.user.mention}\n**Канал:** {interaction.channel.mention}",
        color=discord.Color.red()
    )
    await interaction.channel.send(f"{role_mention}, терміновий виклик!", embed=embed, view=CallModControlView())
    await interaction.followup.send(f"✅ Виклик надіслано!", ephemeral=True)

class CallModControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Взяти виклик", style=discord.ButtonStyle.primary, emoji="🛡️", custom_id="callmod_take_btn_v3")
    async def take_call(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff_or_admin(interaction.user):
            await interaction.response.send_message("❌ Тільки для модераторів!", ephemeral=True)
            return
        await interaction.response.defer()
        button.disabled = True
        add_mod_stat(interaction.guild.id, interaction.user.id)
        await interaction.message.edit(view=self)
        await interaction.channel.send(f"🛡️ Модератор {interaction.user.mention} взяв виклик.")

# ==================== ОЦІНКА ТА ЗАКРИТТЯ ТІКЕТІВ ====================

class TicketRatingView(discord.ui.View):
    def __init__(self, guild_id: int, moderator_id: int, author_id: int, channel: discord.TextChannel):
        super().__init__(timeout=60)
        self.guild_id = guild_id
        self.moderator_id = moderator_id
        self.author_id = author_id
        self.channel = channel

    async def save_rating_and_close(self, interaction: discord.Interaction, rating: int, rating_name: str):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Тільки автор тікета може поставити оцінку!", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        if self.moderator_id:
            add_mod_stat(self.guild_id, self.moderator_id, rating=rating)

        messages = []
        async for msg in self.channel.history(limit=500, oldest_first=True):
            time_str = msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
            messages.append(f"[{time_str}] {msg.author.name}: {msg.content}")
            
        transcript_text = "\n".join(messages)
        file_data = io.BytesIO(transcript_text.encode("utf-8"))
        
        embed = discord.Embed(
            title="📄 Транскрипт закритого тікета",
            description=f"**Сервер:** {interaction.guild.name}\n**Оцінка роботи:** {rating_name} ({rating}/5)",
            color=discord.Color.gold()
        )

        if self.moderator_id:
            mod = interaction.guild.get_member(self.moderator_id)
            if mod:
                try:
                    file_data.seek(0)
                    await mod.send(embed=embed, file=discord.File(file_data, filename=f"transcript-{self.channel.name}.txt"))
                except Exception:
                    pass

        author = interaction.guild.get_member(self.author_id)
        if author:
            try:
                file_data.seek(0)
                await author.send(embed=embed, file=discord.File(file_data, filename=f"transcript-{self.channel.name}.txt"))
            except Exception:
                pass

        await interaction.followup.send(f"✅ Дякуємо за оцінку (**{rating_name}**)!. Тікет закривається...", ephemeral=True)
        await asyncio.sleep(2)
        try:
            await self.channel.delete()
        except Exception:
            pass

    @discord.ui.button(label="Відмінно", style=discord.ButtonStyle.success, emoji="😁", custom_id="rate_5_custom")
    async def rate_excellent(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.save_rating_and_close(interaction, 5, "Відмінно")

    @discord.ui.button(label="Добре", style=discord.ButtonStyle.primary, emoji="🙂", custom_id="rate_4_custom")
    async def rate_good(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.save_rating_and_close(interaction, 4, "Добре")

    @discord.ui.button(label="Погано", style=discord.ButtonStyle.danger, emoji="🙁", custom_id="rate_2_custom")
    async def rate_bad(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.save_rating_and_close(interaction, 2, "Погано")


class ModernTicketModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="Звернення до Модерації")

    subject = discord.ui.TextInput(label="Тема звернення", placeholder="Коротко про проблему", required=True)
    details = discord.ui.TextInput(label="Опишіть ситуацію", style=discord.TextStyle.paragraph, placeholder="Детально розпишіть суть...", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        category = discord.utils.get(guild.categories, name="🎫 ЗВЕРНЕННЯ ДО МОДЕРАЦІЇ")
        if not category:
            category = await guild.create_category("🎫 ЗВЕРНЕННЯ ДО МОДЕРАЦІЇ")

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True)
        }
        for role_name in STAFF_ROLE_NAMES:
            r = discord.utils.get(guild.roles, name=role_name)
            if r:
                overwrites[r] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

        ticket_channel = await guild.create_text_channel(f"🎫-{interaction.user.name.lower()}", category=category, overwrites=overwrites)
        
        mod_role = discord.utils.get(guild.roles, name="🛡️ Модерація (Discord)") or discord.utils.get(guild.roles, name="Модератор")
        role_mention = mod_role.mention if mod_role else "@Модерація"

        embed = discord.Embed(title=f"🎫 Звернення: {self.subject.value}", description=f"**Користувач:** {interaction.user.mention}\n**Опис:** {self.details.value}", color=discord.Color.blurple())
        await ticket_channel.send(f"{interaction.user.mention} | {role_mention}", embed=embed, view=ModernTicketControlView(interaction.user.id))
        await interaction.followup.send(f"✅ Тікет створено -> {ticket_channel.mention}", ephemeral=True)

class ModernTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Створити тікет", style=discord.ButtonStyle.success, emoji="🎫", custom_id="modern_create_ticket_btn_v5")
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ModernTicketModal())

class TransferTicketModal(discord.ui.Modal):
    def __init__(self, view_ref):
        super().__init__(title="Передати тікет іншому модератору")
        self.view_ref = view_ref

    mod_tag = discord.ui.TextInput(label="Вкажіть ID модератора", placeholder="Наприклад: 824368499559497768", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            new_mod_id = int(self.mod_tag.value)
            self.view_ref.assigned_mod_id = new_mod_id
            new_mod = interaction.guild.get_member(new_mod_id)
            mod_name = new_mod.mention if new_mod else f"ID: {new_mod_id}"
            await interaction.response.send_message(f"🔄 Тікет успішно передано модератору **{mod_name}**.")
        except ValueError:
            await interaction.response.send_message("❌ Введіть коректний числовий ID користувача!", ephemeral=True)

class ModernTicketControlView(discord.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=None)
        self.author_id = author_id
        self.assigned_mod_id = None
        self.taken_by_anyone = False

    @discord.ui.button(label="📌 Взяти на розгляд", style=discord.ButtonStyle.primary, custom_id="modern_take_ticket_btn_v6")
    async def take_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff_or_admin(interaction.user):
            await interaction.response.send_message("❌ Недостатньо прав!", ephemeral=True)
            return
        
        if self.taken_by_anyone:
            await interaction.response.send_message("❌ Цей тікет вже хтось узяв на розгляд!", ephemeral=True)
            return

        await interaction.response.defer()
        self.taken_by_anyone = True
        self.assigned_mod_id = interaction.user.id
        button.disabled = True
        await interaction.message.edit(view=self)
        await interaction.channel.send(f"📌 Тікет узяв на розгляд модератор {interaction.user.mention}.")

    @discord.ui.button(label="🔄 Передати тікет", style=discord.ButtonStyle.secondary, custom_id="modern_transfer_ticket_btn_v6")
    async def transfer_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff_or_admin(interaction.user):
            await interaction.response.send_message("❌ Недостатньо прав!", ephemeral=True)
            return
        await interaction.response.send_modal(TransferTicketModal(self))

    @discord.ui.button(label="🔒 Закрити тікет", style=discord.ButtonStyle.danger, custom_id="modern_close_ticket_btn_v6")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff_or_admin(interaction.user) and interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ У вас немає прав!", ephemeral=True)
            return
        
        for child in self.children:
            child.disabled = True
        try:
            await interaction.message.edit(view=self)
        except Exception:
            pass

        embed = discord.Embed(
            title="⭐ Оцінка роботи модератора",
            description=f"Тікет закривається. Будь ласка, оцініть роботу модератора за допомогою кнопок нижче:",
            color=discord.Color.blurple()
        )
        await interaction.response.send_message(embed=embed, view=TicketRatingView(interaction.guild.id, self.assigned_mod_id, self.author_id, interaction.channel))

# ==================== РОЛІ ТА СКАРГИ ====================

class GenderSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Хлопець", style=discord.ButtonStyle.primary, emoji="👦", custom_id="role_boy_btn_v3")
    async def set_boy_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        role = discord.utils.get(interaction.guild.roles, name="Хлопець")
        if not role:
            await interaction.response.send_message("❌ Роль 'Хлопець' не знайдена!", ephemeral=True)
            return
        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message("❌ Роль знято.", ephemeral=True)
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message("✅ Видано роль 'Хлопець'!", ephemeral=True)

    @discord.ui.button(label="Дівчина", style=discord.ButtonStyle.success, emoji="👧", custom_id="role_girl_btn_v3")
    async def set_girl_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        role = discord.utils.get(interaction.guild.roles, name="Дівчина")
        if not role:
            await interaction.response.send_message("❌ Роль 'Дівчина' не знайдена!", ephemeral=True)
            return
        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message("❌ Роль знято.", ephemeral=True)
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message("✅ Видано роль 'Дівчина'!", ephemeral=True)

class ComplaintControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Взяти на розгляд", style=discord.ButtonStyle.primary, emoji="🔍", custom_id="take_c_v4")
    async def take_complaint(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff_or_admin(interaction.user):
            await interaction.response.send_message("❌ Недостатньо прав!", ephemeral=True)
            return
        await interaction.response.defer()
        button.disabled = True
        await interaction.message.edit(view=self)
        await interaction.channel.send(f"🔍 Скаргу взяв {interaction.user.mention}.")

    @discord.ui.button(label="Прийняти", style=discord.ButtonStyle.success, emoji="✅", custom_id="accept_c_v4")
    async def accept_complaint(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff_or_admin(interaction.user):
            await interaction.response.send_message("❌ Недостатньо прав!", ephemeral=True)
            return
        add_mod_stat(interaction.guild.id, interaction.user.id)
        await interaction.response.send_message("✅ Скаргу схвалено.")
        await interaction.channel.edit(archived=True, locked=True)

    @discord.ui.button(label="Відхилити", style=discord.ButtonStyle.danger, emoji="✖️", custom_id="reject_c_v4")
    async def reject_complaint(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff_or_admin(interaction.user):
            await interaction.response.send_message("❌ Недостатньо прав!", ephemeral=True)
            return
        add_mod_stat(interaction.guild.id, interaction.user.id)
        await interaction.response.send_message("❌ Скаргу відхилено.")
        await interaction.channel.edit(archived=True, locked=True)

class ComplaintModal(discord.ui.Modal):
    def __init__(self, category_name: str):
        super().__init__(title=f"Скарга: {category_name}")
        self.category_name = category_name

    reason = discord.ui.TextInput(label="Причина", placeholder="DM, MG", required=True)
    discord_tag = discord.ui.TextInput(label="Discord гравця", placeholder="Нік гравця", required=True)
    essence = discord.ui.TextInput(label="Опис", style=discord.TextStyle.paragraph, placeholder="Опишіть ситуацію", required=True)
    date_p = discord.ui.TextInput(label="Дата", placeholder="05.10.2026, 15:00", required=True)
    proofs = discord.ui.TextInput(label="Докази", style=discord.TextStyle.paragraph, placeholder="Посилання", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if isinstance(interaction.channel, discord.ForumChannel):
            thread_message = await interaction.channel.create_thread(
                name=f"Скарга | {self.discord_tag.value}",
                content=f"Скаргу подав {interaction.user.mention}",
                embed=discord.Embed(title="Скарга на гравця", description=f"**Причина:** {self.reason.value}\n**Опис:** {self.essence.value}", color=discord.Color.red())
            )
            await thread_message.thread.send("Керування скаргою:", view=ComplaintControlView())
            await interaction.followup.send(f"✅ Створено гілку -> {thread_message.thread.mention}", ephemeral=True)

class CreateComplaintView(discord.ui.View):
    def __init__(self, category_name: str):
        super().__init__(timeout=None)
        self.category_name = category_name

    @discord.ui.button(label="Подати скаргу", style=discord.ButtonStyle.primary, emoji="📝", custom_id="open_c_v4")
    async def open_complaint_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ComplaintModal(self.category_name))

# ==================== ЗАЯВКИ НА РОЛІ ====================

class PlayerAppModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="Заявка на роль Гравця")

    age = discord.ui.TextInput(label="Ваш вік", placeholder="Наприклад: 16", required=True)
    nickname = discord.ui.TextInput(label="Ігровий нік / Ім'я", placeholder="Ваше ім'я в грі або на сервері", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        req_channel = None
        for channel in guild.text_channels:
            if any(name in channel.name.lower() for name in ["заявк", "гравц", "player", "application"]):
                req_channel = channel
                break
        if not req_channel: req_channel = interaction.channel

        embed = discord.Embed(title="📥 Заявка на роль Гравець", description=f"**Кандидат:** {interaction.user.mention}\n**Вік:** {self.age.value}\n**Ім'я / Нік:** {self.nickname.value}", color=discord.Color.blue())
        await req_channel.send(embed=embed, view=PlayerAppControlView(interaction.user.id))
        await interaction.followup.send("✅ Заявку надіслано!", ephemeral=True)

class PlayerAppControlView(discord.ui.View):
    def __init__(self, applicant_id: int):
        super().__init__(timeout=None)
        self.applicant_id = applicant_id

    @discord.ui.button(label="Схвалити", style=discord.ButtonStyle.success, emoji="✅", custom_id="p_acc")
    async def accept_app(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff_or_admin(interaction.user): return await interaction.response.send_message("❌ Немає прав!", ephemeral=True)
        guild = interaction.guild
        applicant = guild.get_member(self.applicant_id)
        role = discord.utils.get(guild.roles, name="Гравець")
        if applicant and role:
            try: await applicant.add_roles(role)
            except: pass
        for child in self.children: child.disabled = True
        await interaction.response.edit_message(view=self)
        add_mod_stat(guild.id, interaction.user.id)
        await interaction.channel.send(f"✅ Заявку схвалив {interaction.user.mention}.")

    @discord.ui.button(label="Відхилити", style=discord.ButtonStyle.danger, emoji="❌", custom_id="p_rej")
    async def reject_app(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff_or_admin(interaction.user): return await interaction.response.send_message("❌ Немає прав!", ephemeral=True)
        for child in self.children: child.disabled = True
        await interaction.response.edit_message(view=self)
        add_mod_stat(guild.id, interaction.user.id)
        await interaction.channel.send(f"❌ Заявку відхилив {interaction.user.mention}.")

class PlayerAppPanelView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Отримати роль Гравець", style=discord.ButtonStyle.primary, emoji="🎮", custom_id="p_open")
    async def open_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(PlayerAppModal())

class FactionModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="Запит фракційної ролі")

    nickname = discord.ui.TextInput(label="Вкажіть ваш ігровий нік", placeholder="Taras_Shevchenko", required=True)
    rank = discord.ui.TextInput(label="Вкажіть ігровий ранг (1-10)", placeholder="1", required=True)
    faction = discord.ui.TextInput(label="Оберіть вашу фракцію", placeholder="ВРУ, СБУ, ЗСУ, НПУ, МОЗ, ТСН", required=True)
    proof_url = discord.ui.TextInput(label="Посилання на скріншот статистики", style=discord.TextStyle.paragraph, placeholder="Вставити посилання", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        req_channel = None
        for channel in guild.text_channels:
            if any(name in channel.name.lower() for name in ["заявк", "фракц", "ролі", "application"]):
                req_channel = channel
                break
        if not req_channel: req_channel = interaction.channel

        embed = discord.Embed(
            title="📥 Новий запит фракційної ролі",
            description=f"**Гравець:** {interaction.user.mention}\n**Нік:** `{self.nickname.value}`\n**Ранг:** `{self.rank.value}`\n**Фракція:** `{self.faction.value}`\n**Скріншот:** [Переглянути]({self.proof_url.value})",
            color=discord.Color.gold()
        )
        await req_channel.send(embed=embed, view=FactionAppControlView(interaction.user.id, self.faction.value))
        await interaction.followup.send("✅ Запит на фракційну роль надіслано!", ephemeral=True)

class FactionAppControlView(discord.ui.View):
    def __init__(self, applicant_id: int, faction_name: str):
        super().__init__(timeout=None)
        self.applicant_id = applicant_id
        self.faction_name = faction_name

    @discord.ui.button(label="Схвалити", style=discord.ButtonStyle.success, emoji="✅", custom_id="f_acc")
    async def accept_app(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff_or_admin(interaction.user): return await interaction.response.send_message("❌ Немає прав!", ephemeral=True)
        guild = interaction.guild
        applicant = guild.get_member(self.applicant_id)
        role = discord.utils.get(guild.roles, name=self.faction_name) or discord.utils.get(guild.roles, name="Фракція")
        if applicant and role:
            try: await applicant.add_roles(role)
            except: pass
        for child in self.children: child.disabled = True
        await interaction.response.edit_message(view=self)
        add_mod_stat(guild.id, interaction.user.id)
        await interaction.channel.send(f"✅ Заявку схвалив {interaction.user.mention}. Роль видано.")

    @discord.ui.button(label="Відхилити", style=discord.ButtonStyle.danger, emoji="❌", custom_id="f_rej")
    async def reject_app(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff_or_admin(interaction.user): return await interaction.response.send_message("❌ Немає прав!", ephemeral=True)
        for child in self.children: child.disabled = True
        await interaction.response.edit_message(view=self)
        add_mod_stat(guild.id, interaction.user.id)
        await interaction.channel.send(f"❌ Заявку відхилив {interaction.user.mention}.")

class FactionPanelView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Подати заявку", style=discord.ButtonStyle.primary, emoji="🟦", custom_id="f_open")
    async def open_faction_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(FactionModal())

# Запуск бота через змінну середовища (Environment Variable)
bot.run(os.getenv('TOKEN'))
