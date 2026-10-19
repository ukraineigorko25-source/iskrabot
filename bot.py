import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import sqlite3
import io
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

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# ==================== БАЗА ДАНИХ (SQLite) ====================
db = sqlite3.connect("bot_database.db", check_same_thread=False)
cursor = db.cursor()

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
        """, (guild_id, moderator_id, rating, 1 if rating > 0 else 0))
    db.commit()

def is_staff_or_admin(member: discord.Member) -> bool:
    if member.guild_permissions.administrator or member.guild_permissions.manage_guild:
        return True
    for role in member.roles:
        if role.name in STAFF_ROLE_NAMES:
            return True
    return False

# ==================== ЛОГИ МОДЕРАЦІЇ ====================

async def send_mod_log(guild: discord.Guild, text: str, color=discord.Color.red()):
    log_channel = None
    for channel in guild.text_channels:
        if any(name in channel.name.lower() for name in ["лог", "log", "покарання", "варн", "мод-лог"]):
            log_channel = channel
            break
    
    if log_channel:
        embed = discord.Embed(title="🛡️ Лог Модерації", description=text, color=color)
        embed.timestamp = discord.utils.utcnow()
        try: await log_channel.send(embed=embed)
        except Exception: pass

# ==================== ВЕБ-ПАНЕЛЬ ====================

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

# ==================== ОСНОВНИЙ БОТ ====================

class IskraBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        self.add_view(CreateComplaintView())
        self.add_view(ComplaintControlView())
        self.add_view(ModernTicketView())
        self.add_view(GenderSelectView())
        self.add_view(CallModControlView())
        self.add_view(FactionPanelView())
        self.add_view(PlayerAppPanelView())
        self.add_view(SquidGameView())
        
        try:
            synced = await self.tree.sync()
            print(f"✅ Успішно синхронізовано команд: {len(synced)}")
        except Exception as e:
            print(f"❌ Помилка синхронізації: {e}")

bot = IskraBot()

@bot.event
async def on_ready():
    print(f"Бот {bot.user} успішно запущений!")
    asyncio.create_task(start_web_server())

    # АВТОМАТИЧНЕ СТВОРЕННЯ ПАНЕЛІ У ФОРУМАХ (ЯК У ВЕРБОБОТА)
    for guild in bot.guilds:
        for channel in guild.forum_channels:
            if "скарг" in channel.name.lower() or "покарання" in channel.name.lower():
                try:
                    # Перевіряємо, чи бот вже створював тут пост
                    async for thread in channel.archived_threads(limit=10):
                        pass
                    threads = channel.threads
                    bot_posted = any(t.owner and t.owner.id == bot.user.id for t in threads)
                    
                    if not bot_posted:
                        embed = discord.Embed(
                            title=f"💬 Скарги та правила ({channel.name})",
                            description=(
                                "❓ У цьому каналі ви можете створити скаргу.\n"
                                "Щоб створити скаргу, натисніть на кнопку нижче.\n\n"
                                "1. **Загальні вимоги до скарг:**\n"
                                "• чіткі докази порушення\n"
                                "• опис суті ситуації\n"
                                "• нікнейми учасників\n\n"
                                "2. Скарга повинна бути подана учасником ситуації.\n"
                                "3. Скарга повинна бути написана коректно та адекватно."
                            ),
                            color=discord.Color.red()
                        )
                        await channel.create_thread(
                            name="📌 | Інструкція та подача скарги",
                            embed=embed,
                            view=CreateComplaintView()
                        )
                except Exception as e:
                    print(f"Помилка автоматичного створення поста у форумі {channel.name}: {e}")

@bot.event
async def on_member_join(member: discord.Member):
    welcome_channel = None
    for channel in member.guild.text_channels:
        if any(name in channel.name.lower() for name in ["вітання", "welcome", "загальний", "чат"]):
            welcome_channel = channel
            break
    
    if welcome_channel:
        embed = discord.Embed(
            title=f"👋 Вітаємо на сервері {member.guild.name}!",
            description=f"Привіт, {member.mention}! Раді бачити тебе на нашому сервері.\nОзнайомся з правилами та бажаємо приємної гри!",
            color=discord.Color.blurple()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        try: await welcome_channel.send(embed=embed)
        except Exception: pass

# ==================== СИСТЕМА СКАРГ ДЛЯ ФОРУМІВ ====================

class SetNicknameModal(discord.ui.Modal):
    def __init__(self): super().__init__(title="Встановлення нікнейму")
    nick = discord.ui.TextInput(label="Вкажіть ваш ігровий нікнейм", placeholder="Приклад: Taras_Shevchenko", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        cursor.execute("INSERT OR REPLACE INTO user_nicknames (user_id, ingame_nick) VALUES (?, ?)", (interaction.user.id, self.nick.value))
        db.commit()
        await interaction.response.send_message(f"✅ Ваш ігровий нікнейм успішно встановлено на **{self.nick.value}**.", ephemeral=True)

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
    def __init__(self): super().__init__(timeout=None)

    @discord.ui.button(label="Взяти на розгляд", style=discord.ButtonStyle.primary, emoji="🔍", custom_id="take_c_v5")
    async def take(self, interaction: discord.Interaction, button):
        if not is_staff_or_admin(interaction.user): return await interaction.response.send_message("❌ Немає прав!", ephemeral=True)
        await interaction.response.defer()
        button.disabled = True
        await interaction.message.edit(view=self)
        await interaction.channel.send(f"🔍 Скаргу взяв на розгляд адміністратор {interaction.user.mention}.")

    @discord.ui.button(label="Прийняти", style=discord.ButtonStyle.success, emoji="✅", custom_id="accept_c_v5")
    async def accept(self, interaction: discord.Interaction, button):
        if not is_staff_or_admin(interaction.user): return await interaction.response.send_message("❌ Немає прав!", ephemeral=True)
        add_mod_stat(interaction.guild.id, interaction.user.id)
        await interaction.response.send_message(f"✅ **Скаргу було схвалено** адміністратором {interaction.user.mention}.")
        await send_mod_log(interaction.guild, f"✅ **СХВАЛЕНО СКАРГУ**\n👮 Адмін: {interaction.user.mention}\nКанал: {interaction.channel.mention}", discord.Color.green())

    @discord.ui.button(label="Відхилити", style=discord.ButtonStyle.danger, emoji="❌", custom_id="reject_c_v5")
    async def reject(self, interaction: discord.Interaction, button):
        if not is_staff_or_admin(interaction.user): return await interaction.response.send_message("❌ Немає прав!", ephemeral=True)
        add_mod_stat(interaction.guild.id, interaction.user.id)
        await interaction.response.send_message(f"❌ **Скаргу було відхилено** адміністратором {interaction.user.mention}.")
        await send_mod_log(interaction.guild, f"❌ **ВІДХИЛЕНО СКАРГУ**\n👮 Адмін: {interaction.user.mention}\nКанал: {interaction.channel.mention}")

    @discord.ui.button(label="Вимкнути офтоп", style=discord.ButtonStyle.secondary, emoji="💬", custom_id="close_offtop_v5")
    async def close_offtop(self, interaction: discord.Interaction, button):
        if not is_staff_or_admin(interaction.user): return await interaction.response.send_message("❌ Немає прав!", ephemeral=True)
        await interaction.response.send_message("🔒 **Обговорення закрито.** Допис переведено в режим читання.")
        if isinstance(interaction.channel, discord.Thread):
            await interaction.channel.edit(locked=True)

class ForumComplaintModal(discord.ui.Modal):
    def __init__(self, channel_name: str, ingame_nick: str):
        super().__init__(title=f"Скарга: {channel_name[:18]}")
        self.channel_name = channel_name
        self.ingame_nick = ingame_nick

    reason = discord.ui.TextInput(label="Причина скарги", placeholder="Приклад: DM, MG, PG, Образи тощо", required=True)
    target_discord = discord.ui.TextInput(label="Вкажіть Discord гравця / порушника", placeholder="Приклад: 2tired", required=True)
    essence = discord.ui.TextInput(label="Опис скарги", style=discord.TextStyle.paragraph, placeholder="Приклад: Flood", required=True)
    date_p = discord.ui.TextInput(label="Дата порушення", placeholder="Приклад: 19.10.2026, 20:44", required=True)
    proofs = discord.ui.TextInput(label="Докази", style=discord.TextStyle.paragraph, placeholder="Посилання на скріноти/відео", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild

        c_id = get_next_complaint_id(guild.id)
        thread_name = f"#{c_id} | {self.target_discord.value} | {self.reason.value}"

        embed = discord.Embed(
            title=f"Скарга ({self.channel_name}) No{c_id}",
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

        if isinstance(interaction.channel, discord.ForumChannel):
            thread_with_msg = await interaction.channel.create_thread(
                name=thread_name,
                embed=embed,
                view=view
            )
            await interaction.followup.send(f"✅ Вашу скаргу успішно створено у форумі -> {thread_with_msg.thread.mention}", ephemeral=True)
        elif isinstance(interaction.channel, discord.Thread) and isinstance(interaction.channel.parent, discord.ForumChannel):
            forum = interaction.channel.parent
            thread_with_msg = await forum.create_thread(
                name=thread_name,
                embed=embed,
                view=view
            )
            await interaction.followup.send(f"✅ Вашу скаргу успішно створено у форумі -> {thread_with_msg.thread.mention}", ephemeral=True)
        else:
            await interaction.channel.send(embed=embed, view=view)
            await interaction.followup.send(f"✅ Скаргу надіслано в канал {interaction.channel.mention}", ephemeral=True)

class CreateComplaintView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Подати скаргу", style=discord.ButtonStyle.primary, emoji="📝", custom_id="open_c_main_btn")
    async def open_complaint_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        cursor.execute("SELECT ingame_nick FROM user_nicknames WHERE user_id = ?", (interaction.user.id,))
        row = cursor.fetchone()
        
        if not row:
            return await interaction.response.send_message(
                "❌ **Помилка:** Ви повинні вказати ваш ігровий нікнейм перед подачею скарги. Скористайтеся кнопкою **\"Вказати нікнейм\"**.",
                ephemeral=True
            )

        channel_name = interaction.channel.name
        if isinstance(interaction.channel, discord.Thread) and interaction.channel.parent:
            channel_name = interaction.channel.parent.name

        await interaction.response.send_modal(ForumComplaintModal(channel_name, row[0]))

    @discord.ui.button(label="Вказати нікнейм", style=discord.ButtonStyle.secondary, emoji="✏️", custom_id="set_nick_main_btn")
    async def open_set_nick_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SetNicknameModal())

# ==================== СИСТЕМА ТІКЕТІВ ====================

class TicketRatingView(discord.ui.View):
    def __init__(self, guild_id: int, moderator_id: int, author_id: int, channel: discord.TextChannel):
        super().__init__(timeout=60)
        self.guild_id = guild_id
        self.moderator_id = moderator_id
        self.author_id = author_id
        self.channel = channel

    async def save_rating_and_close(self, interaction: discord.Interaction, rating: int, rating_name: str):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("❌ Тільки автор тікета може поставити оцінку!", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        if self.moderator_id: add_mod_stat(self.guild_id, self.moderator_id, rating=rating)

        messages = []
        async for msg in self.channel.history(limit=500, oldest_first=True):
            messages.append(f"[{msg.created_at.strftime('%Y-%m-%d %H:%M:%S')}] {msg.author.name}: {msg.content}")
            
        file_data = io.BytesIO("\n".join(messages).encode("utf-8"))
        embed = discord.Embed(title="📄 Транскрипт закритого тікета", description=f"**Сервер:** {interaction.guild.name}\n**Оцінка:** {rating_name} ({rating}/5)", color=discord.Color.gold())

        author = interaction.guild.get_member(self.author_id)
        if author:
            try:
                file_data.seek(0)
                await author.send(embed=embed, file=discord.File(file_data, filename=f"transcript-{self.channel.name}.txt"))
            except Exception: pass

        await interaction.followup.send(f"✅ Дякуємо за оцінку (**{rating_name}**)! Тікет закривається...", ephemeral=True)
        await asyncio.sleep(2)
        try: await self.channel.delete()
        except Exception: pass

    @discord.ui.button(label="Відмінно", style=discord.ButtonStyle.success, emoji="😁", custom_id="rate_5_custom")
    async def rate_5(self, interaction, button): await self.save_rating_and_close(interaction, 5, "Відмінно")

    @discord.ui.button(label="Добре", style=discord.ButtonStyle.primary, emoji="🙂", custom_id="rate_4_custom")
    async def rate_4(self, interaction, button): await self.save_rating_and_close(interaction, 4, "Добре")

    @discord.ui.button(label="Погано", style=discord.ButtonStyle.danger, emoji="🙁", custom_id="rate_2_custom")
    async def rate_2(self, interaction, button): await self.save_rating_and_close(interaction, 2, "Погано")

class ModernTicketModal(discord.ui.Modal):
    def __init__(self): super().__init__(title="Звернення до Модерації")
    subject = discord.ui.TextInput(label="Тема звернення", placeholder="Коротко про проблему", required=True)
    details = discord.ui.TextInput(label="Опишіть ситуацію", style=discord.TextStyle.paragraph, placeholder="Детально...", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        category = discord.utils.get(guild.categories, name="🎫 ЗВЕРНЕННЯ ДО МОДЕРАЦІЇ") or await guild.create_category("🎫 ЗВЕРНЕННЯ ДО МОДЕРАЦІЇ")

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True)
        }
        ticket_channel = await guild.create_text_channel(f"🎫-{interaction.user.name.lower()}", category=category, overwrites=overwrites)
        embed = discord.Embed(title=f"🎫 Звернення: {self.subject.value}", description=f"**Користувач:** {interaction.user.mention}\n**Опис:** {self.details.value}", color=discord.Color.blurple())
        await ticket_channel.send(f"{interaction.user.mention}", embed=embed, view=ModernTicketControlView(interaction.user.id))
        await interaction.followup.send(f"✅ Тікет створено -> {ticket_channel.mention}", ephemeral=True)

class ModernTicketView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Створити тікет", style=discord.ButtonStyle.success, emoji="🎫", custom_id="modern_create_ticket_btn_v5")
    async def create_ticket(self, interaction: discord.Interaction, button):
        await interaction.response.send_modal(ModernTicketModal())

class ModernTicketControlView(discord.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=None)
        self.author_id = author_id
        self.assigned_mod_id = None

    @discord.ui.button(label="📌 Взяти на розгляд", style=discord.ButtonStyle.primary, custom_id="modern_take_ticket_btn_v6")
    async def take_ticket(self, interaction: discord.Interaction, button):
        if not is_staff_or_admin(interaction.user): return await interaction.response.send_message("❌ Недостатньо прав!", ephemeral=True)
        self.assigned_mod_id = interaction.user.id
        button.disabled = True
        await interaction.message.edit(view=self)
        await interaction.channel.send(f"📌 Тікет узяв на розгляд модератор {interaction.user.mention}.")

    @discord.ui.button(label="🔒 Закрити тікет", style=discord.ButtonStyle.danger, custom_id="modern_close_ticket_btn_v6")
    async def close_ticket(self, interaction: discord.Interaction, button):
        if not is_staff_or_admin(interaction.user) and interaction.user.id != self.author_id:
            return await interaction.response.send_message("❌ У вас немає прав!", ephemeral=True)
        embed = discord.Embed(title="⭐ Оцінка роботи модератора", description="Оцініть роботу модератора нижче:", color=discord.Color.blurple())
        await interaction.response.send_message(embed=embed, view=TicketRatingView(interaction.guild.id, self.assigned_mod_id, self.author_id, interaction.channel))

# ==================== СЛЕШ-КОМАНДИ ====================

@bot.tree.command(name="ticketpanel", description="Створити панель тікетів")
@app_commands.default_permissions(administrator=True)
async def ticketpanel(interaction: discord.Interaction):
    embed = discord.Embed(title="🛡️ Звернення до Модерації Discord", description="Натисніть кнопку нижче, щоб відкрити приватний тікет.", color=discord.Color.blurple())
    await interaction.channel.send(embed=embed, view=ModernTicketView())
    await interaction.response.send_message("✅ Панель тікетів створена!", ephemeral=True)

@bot.tree.command(name="playerpanel", description="Створити панель заявки на роль гравця")
@app_commands.default_permissions(administrator=True)
async def playerpanel(interaction: discord.Interaction):
    embed = discord.Embed(title="🎮 Отримання ролі Гравець", description="Натисніть кнопку нижче, щоб подати заявку.", color=discord.Color.blue())
    await interaction.channel.send(embed=embed, view=PlayerAppPanelView())
    await interaction.response.send_message("✅ Панель ролі гравця створена!", ephemeral=True)

@bot.tree.command(name="factionpanel", description="Створити панель подачі заявки на фракційну роль")
@app_commands.default_permissions(administrator=True)
async def factionpanel(interaction: discord.Interaction):
    embed = discord.Embed(title="🏛️ Отримання ролі в організації", description="Натисніть кнопку нижче, щоб подати заявку.", color=discord.Color.gold())
    await interaction.channel.send(embed=embed, view=FactionPanelView())
    await interaction.response.send_message("✅ Панель фракцій створена!", ephemeral=True)

@bot.tree.command(name="genderpanel", description="Створити панель вибору ролі (хлопець / дівчина)")
@app_commands.default_permissions(administrator=True)
async def genderpanel(interaction: discord.Interaction):
    embed = discord.Embed(title="🎭 Вибір ролі (Стать)", description="Натисніть кнопку, щоб отримати роль:", color=discord.Color.magenta())
    await interaction.channel.send(embed=embed, view=GenderSelectView())
    await interaction.response.send_message("✅ Панель ролей створена!", ephemeral=True)

@bot.tree.command(name="squidgame", description="Запустити мінігру «Ігра в кальмара»")
@app_commands.default_permissions(manage_messages=True)
async def squidgame_cmd(interaction: discord.Interaction):
    embed = discord.Embed(title="🦑 Гра в кальмара", description="Натисніть кнопку, щоб розпочати!", color=discord.Color.red())
    await interaction.channel.send(embed=embed, view=SquidGameView())
    await interaction.response.send_message("✅ Панель мінігри створено!", ephemeral=True)

@bot.tree.command(name="modstats", description="Переглянути рейтинг модераторів")
@app_commands.default_permissions(manage_messages=True)
async def modstats(interaction: discord.Interaction):
    cursor.execute("SELECT moderator_id, closed_count, total_rating, rating_count FROM mod_stats WHERE guild_id = ? ORDER BY closed_count DESC", (interaction.guild.id,))
    rows = cursor.fetchall()
    embed = discord.Embed(title="🏆 Рейтинг модераторів", color=discord.Color.gold())
    if not rows: embed.description = "Статистика порожня."
    else:
        for idx, (m_id, closed, t_rating, r_count) in enumerate(rows, 1):
            user = interaction.guild.get_member(m_id)
            name = user.display_name if user else f"ID: {m_id}"
            avg_rating = round((t_rating or 0) / (r_count or 1), 1) if r_count else 0.0
            embed.add_field(name=f"#{idx} | {name}", value=f"📌 Закрито: **{closed}** | ⭐ Оцінка: **{avg_rating}/5.0**", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="ban", description="Заблокувати користувача")
@app_commands.default_permissions(ban_members=True)
async def ban_member(interaction: discord.Interaction, member: discord.Member, reason: str = "Причина не вказана"):
    if not is_staff_or_admin(interaction.user): return await interaction.response.send_message("❌ Немає прав!", ephemeral=True)
    await member.ban(reason=reason)
    add_mod_stat(interaction.guild.id, interaction.user.id)
    await interaction.response.send_message(f"🔨 Заблоковано {member.mention}.")
    await send_mod_log(interaction.guild, f"🔨 **БАН** | Порушник: {member.mention} | Адмін: {interaction.user.mention} | Причина: {reason}")

@bot.tree.command(name="mute", description="Замутити користувача")
@app_commands.default_permissions(moderate_members=True)
async def mute_member(interaction: discord.Interaction, member: discord.Member, minutes: int, reason: str = "Причина не вказана"):
    if not is_staff_or_admin(interaction.user): return await interaction.response.send_message("❌ Немає прав!", ephemeral=True)
    await member.timeout(timedelta(minutes=minutes), reason=reason)
    add_mod_stat(interaction.guild.id, interaction.user.id)
    await interaction.response.send_message(f"🔇 Замучено {member.mention} на {minutes} хв.")
    await send_mod_log(interaction.guild, f"🔇 **МУТ** | Порушник: {member.mention} | Час: {minutes} хв | Причина: {reason}")

@bot.tree.command(name="warn", description="Видати варн")
@app_commands.default_permissions(moderate_members=True)
async def warn_member(interaction: discord.Interaction, member: discord.Member, reason: str = "Причина не вказана"):
    if not is_staff_or_admin(interaction.user): return await interaction.response.send_message("❌ Немає прав!", ephemeral=True)
    cursor.execute("INSERT INTO warns (guild_id, user_id, warn_count) VALUES (?, ?, 1) ON CONFLICT(guild_id, user_id) DO UPDATE SET warn_count = warn_count + 1", (interaction.guild.id, member.id))
    db.commit()
    cursor.execute("SELECT warn_count FROM warns WHERE guild_id = ? AND user_id = ?", (interaction.guild.id, member.id))
    total_warns = cursor.fetchone()[0]
    add_mod_stat(interaction.guild.id, interaction.user.id)
    await interaction.response.send_message(f"⚠️ Видано варн {member.mention} [{total_warns}/3].")
    await send_mod_log(interaction.guild, f"⚠️ **ВАРН** | Користувач: {member.mention} [{total_warns}/3] | Причина: {reason}")

# Допоміжні UI класи
class GenderSelectView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Хлопець", style=discord.ButtonStyle.primary, emoji="👦", custom_id="role_boy_btn_v3")
    async def boy(self, interaction, b):
        role = discord.utils.get(interaction.guild.roles, name="Хлопець")
        if role:
            if role in interaction.user.roles: await interaction.user.remove_roles(role)
            else: await interaction.user.add_roles(role)
            await interaction.response.send_message("✅ Роль оновлено!", ephemeral=True)

    @discord.ui.button(label="Дівчина", style=discord.ButtonStyle.success, emoji="👧", custom_id="role_girl_btn_v3")
    async def girl(self, interaction, b):
        role = discord.utils.get(interaction.guild.roles, name="Дівчина")
        if role:
            if role in interaction.user.roles: await interaction.user.remove_roles(role)
            else: await interaction.user.add_roles(role)
            await interaction.response.send_message("✅ Роль оновлено!", ephemeral=True)

class CallModControlView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Взяти виклик", style=discord.ButtonStyle.primary, emoji="🛡️", custom_id="callmod_take_btn_v3")
    async def take(self, interaction, b):
        if not is_staff_or_admin(interaction.user): return await interaction.response.send_message("❌ Немає прав!", ephemeral=True)
        await interaction.response.defer()
        b.disabled = True
        await interaction.message.edit(view=self)
        await interaction.channel.send(f"🛡️ {interaction.user.mention} прийняв виклик.")

class SquidGameView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="🦑 Почати 'Ігру в кальмара'", style=discord.ButtonStyle.danger, emoji="🎮", custom_id="start_squid_game_main")
    async def start(self, interaction, b):
        await interaction.response.send_message(embed=discord.Embed(title="🦑 Гра розпочата!", description="Учасники проходять раунд «Тихіше їдеш — далі будеш»...", color=discord.Color.red()))

class PlayerAppPanelView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
class FactionPanelView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)

bot.run(os.getenv('TOKEN'))
