import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import sqlite3
import io
import os
from datetime import timedelta
from aiohttp import web

DEVELOPER_ID = 824368499559497768

STAFF_ROLE_NAMES = [
    "Керівник діскорд", "Заступник керівника діскорд", "Діскорд майстер",
    "Спеціальний модератор діскорд", "Головний Модератор", "Заступник Головного Модератора",
    "Куратор Модерація", "Старший Модератор", "Модератор", "Молодший Модератор",
    "ГМ", "ЗГМ", "КМ", "СМ", "МД", "ММД", "🛡️ Модерація (Discord)",
    "Власник", "Керівник проєкту", "Спеціальний адміністратор",
    "Головний Адміністратор", "Заступник Головного Адміністратора", "ГА", "ЗГА"
]

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

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

def get_next_complaint_id(guild_id: int) -> int:
    cursor.execute("SELECT counter FROM complaint_counter WHERE guild_id = ?", (guild_id,))
    row = cursor.fetchone()
    if row:
        new_id = row[0] + 1
        cursor.execute("UPDATE counter FROM complaint_counter WHERE guild_id = ?", (new_id, guild_id))
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
        cursor.execute("UPDATE mod_stats SET closed_count = ?, total_rating = ?, rating_count = ? WHERE guild_id = ? AND moderator_id = ?", (closed, t_rating, r_count, guild_id, moderator_id))
    else:
        cursor.execute("INSERT INTO mod_stats (guild_id, moderator_id, closed_count, total_rating, rating_count) VALUES (?, ?, 1, ?, ?)", (guild_id, moderator_id, rating, 1 if rating > 0 else 0))
    db.commit()

def is_staff_or_admin(member: discord.Member) -> bool:
    if member.guild_permissions.administrator or member.guild_permissions.manage_guild:
        return True
    return any(role.name in STAFF_ROLE_NAMES for role in member.roles)

async def send_mod_log(guild: discord.Guild, text: str, color=discord.Color.red()):
    for channel in guild.text_channels:
        if any(name in channel.name.lower() for name in ["лог", "log", "покарання", "варн", "мод-лог"]):
            embed = discord.Embed(title="🛡️ Лог Модерації", description=text, color=color)
            embed.timestamp = discord.utils.utcnow()
            try: await channel.send(embed=embed)
            except: pass
            break

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

class IskraBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        self.add_view(CreateComplaintView())
        self.add_view(ComplaintControlView())
        self.add_view(ModernTicketView())
        try:
            synced = await self.tree.sync()
            print(f"✅ Синхронізовано команд: {len(synced)}")
        except Exception as e:
            print(f"❌ Помилка: {e}")

bot = IskraBot()

@bot.event
async def on_ready():
    print(f"Бот {bot.user} запущений!")
    asyncio.create_task(start_web_server())

# ==================== СИСТЕМА СКАРГ ====================

class SetNicknameModal(discord.ui.Modal):
    def __init__(self): super().__init__(title="Встановлення нікнейму")
    nick = discord.ui.TextInput(label="Вкажіть ваш ігровий нікнейм", placeholder="Приклад: Taras_Shevchenko", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        cursor.execute("INSERT OR REPLACE INTO user_nicknames (user_id, ingame_nick) VALUES (?, ?)", (interaction.user.id, self.nick.value))
        db.commit()
        await interaction.response.send_message(f"✅ Ваш ігровий нікнейм успішно встановлено на **{self.nick.value}**.", ephemeral=True)

class AdminSelectDropdown(discord.ui.Select):
    def __init__(self, guild: discord.Guild):
        options = [discord.SelectOption(label=m.display_name, value=str(m.id), description=f"@{m.name}") for m in guild.members if is_staff_or_admin(m) and not m.bot][:25]
        if not options: options.append(discord.SelectOption(label="Немає адмінів", value="0"))
        super().__init__(placeholder="Обрати відповідального адміністратора", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if not is_staff_or_admin(interaction.user): return await interaction.response.send_message("❌ Недостатньо прав!", ephemeral=True)
        admin_member = interaction.guild.get_member(int(self.values[0]))
        await interaction.response.send_message(f"👤 Відповідальним призначено: {admin_member.mention if admin_member else 'Адміністратор'}")

class ComplaintControlView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)

    @discord.ui.button(label="Взяти на розгляд", style=discord.ButtonStyle.primary, emoji="🔍", custom_id="take_c")
    async def take(self, interaction, button):
        if not is_staff_or_admin(interaction.user): return await interaction.response.send_message("❌ Немає прав!", ephemeral=True)
        await interaction.response.defer()
        button.disabled = True
        await interaction.message.edit(view=self)
        await interaction.channel.send(f"🔍 Скаргу взяв на розгляд {interaction.user.mention}.")

    @discord.ui.button(label="Прийняти", style=discord.ButtonStyle.success, emoji="✅", custom_id="accept_c")
    async def accept(self, interaction, button):
        if not is_staff_or_admin(interaction.user): return await interaction.response.send_message("❌ Немає прав!", ephemeral=True)
        add_mod_stat(interaction.guild.id, interaction.user.id)
        await interaction.response.send_message(f"✅ Скаргу схвалено адміністратором {interaction.user.mention}.")
        await send_mod_log(interaction.guild, f"✅ **СХВАЛЕНО СКАРГУ**\n👮 Адмін: {interaction.user.mention}\nКанал: {interaction.channel.mention}", discord.Color.green())

    @discord.ui.button(label="Відхилити", style=discord.ButtonStyle.danger, emoji="❌", custom_id="reject_c")
    async def reject(self, interaction, button):
        if not is_staff_or_admin(interaction.user): return await interaction.response.send_message("❌ Немає прав!", ephemeral=True)
        add_mod_stat(interaction.guild.id, interaction.user.id)
        await interaction.response.send_message(f"❌ Скаргу відхилено адміністратором {interaction.user.mention}.")
        await send_mod_log(interaction.guild, f"❌ **ВІДХИЛЕНО СКАРГУ**\n👮 Адмін: {interaction.user.mention}\nКанал: {interaction.channel.mention}")

class ForumComplaintModal(discord.ui.Modal):
    def __init__(self, channel_name: str, ingame_nick: str):
        super().__init__(title=f"Скарга: {channel_name[:18]}")
        self.channel_name = channel_name
        self.ingame_nick = ingame_nick

    reason = discord.ui.TextInput(label="Причина скарги", placeholder="DM, MG, PG тощо", required=True)
    target_discord = discord.ui.TextInput(label="Discord порушника", placeholder="2tired / @user", required=True)
    essence = discord.ui.TextInput(label="Опис ситуації", style=discord.TextStyle.paragraph, placeholder="Детально...", required=True)
    date_p = discord.ui.TextInput(label="Дата порушення", placeholder="19.10.2026, 20:44", required=True)
    proofs = discord.ui.TextInput(label="Докази (посилання)", style=discord.TextStyle.paragraph, placeholder="Imgur / YouTube", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        c_id = get_next_complaint_id(guild.id)
        thread_name = f"#{c_id} | {self.target_discord.value} | {self.reason.value}"

        embed = discord.Embed(title=f"📋 Скарга ({self.channel_name}) No{c_id}", color=discord.Color.dark_theme())
        embed.description = (
            f"**Автор:** {self.ingame_nick} ({interaction.user.mention})\n"
            f"**Порушник:** {self.target_discord.value}\n"
            f"**Причина:** {self.reason.value}\n"
            f"**Суть:** {self.essence.value}\n"
            f"**Дата:** {self.date_p.value}\n"
            f"**Докази:** {self.proofs.value}"
        )
        embed.set_footer(text=f"Подано: {discord.utils.utcnow().strftime('%d.%m.%Y, %H:%M:%S')}")

        view = ComplaintControlView()
        view.add_item(AdminSelectDropdown(guild))

        target_channel = interaction.channel
        if isinstance(target_channel, discord.Thread) and target_channel.parent:
            target_channel = target_channel.parent

        if isinstance(target_channel, discord.ForumChannel):
            thread = await target_channel.create_thread(name=thread_name, embed=embed, view=view)
            await interaction.followup.send(f"✅ Скаргу створено у гілці -> {thread.thread.mention}", ephemeral=True)
        else:
            msg = await target_channel.send(embed=embed, view=view)
            await interaction.followup.send("✅ Скаргу успішно надіслано!", ephemeral=True)

class CreateComplaintView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)

    @discord.ui.button(label="Подати скаргу", style=discord.ButtonStyle.primary, emoji="📝", custom_id="open_c")
    async def open_modal(self, interaction, button):
        cursor.execute("SELECT ingame_nick FROM user_nicknames WHERE user_id = ?", (interaction.user.id,))
        row = cursor.fetchone()
        if not row:
            return await interaction.response.send_message("❌ Будь ласка, спочатку вкажіть ваш ігровий нікнейм кнопкою нижче!", ephemeral=True)
        
        ch_name = interaction.channel.name
        if isinstance(interaction.channel, discord.Thread) and interaction.channel.parent:
            ch_name = interaction.channel.parent.name
        await interaction.response.send_modal(ForumComplaintModal(ch_name, row[0]))

    @discord.ui.button(label="Вказати нікнейм", style=discord.ButtonStyle.secondary, emoji="✏️", custom_id="set_nick")
    async def open_nick(self, interaction, button):
        await interaction.response.send_modal(SetNicknameModal())

# ==================== ТІКЕТИ ====================

class TicketRatingView(discord.ui.View):
    def __init__(self, guild_id, mod_id, author_id, channel):
        super().__init__(timeout=60)
        self.guild_id, self.mod_id, self.author_id, self.channel = guild_id, mod_id, author_id, channel

    async def close_ticket(self, interaction, rating, name):
        if interaction.user.id != self.author_id: return await interaction.response.send_message("❌ Тільки автор тікета може оцінити!", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        if self.mod_id: add_mod_stat(self.guild_id, self.mod_id, rating=rating)
        
        messages = [f"[{msg.created_at.strftime('%Y-%m-%d %H:%M:%S')}] {msg.author.name}: {msg.content}" async for msg in self.channel.history(limit=500, oldest_first=True)]
        file_data = io.BytesIO("\n".join(messages).encode("utf-8"))
        
        author = interaction.guild.get_member(self.author_id)
        if author:
            try:
                file_data.seek(0)
                await author.send(embed=discord.Embed(title="📄 Транскрипт тікета", description=f"Оцінка: {name} ({rating}/5)", color=discord.Color.gold()), file=discord.File(file_data, filename="transcript.txt"))
            except: pass

        await interaction.followup.send("✅ Дякуємо! Тікет закривається...", ephemeral=True)
        await asyncio.sleep(2)
        try: await self.channel.delete()
        except: pass

    @discord.ui.button(label="Відмінно", style=discord.ButtonStyle.success, emoji="😁")
    async def r5(self, i, b): await self.close_ticket(i, 5, "Відмінно")
    @discord.ui.button(label="Добре", style=discord.ButtonStyle.primary, emoji="🙂")
    async def r4(self, i, b): await self.close_ticket(i, 4, "Добре")
    @discord.ui.button(label="Погано", style=discord.ButtonStyle.danger, emoji="🙁")
    async def r2(self, i, b): await self.close_ticket(i, 2, "Погано")

class ModernTicketModal(discord.ui.Modal):
    def __init__(self): super().__init__(title="Звернення до Модерації")
    subject = discord.ui.TextInput(label="Тема звернення", placeholder="Проблема", required=True)
    details = discord.ui.TextInput(label="Опис", style=discord.TextStyle.paragraph, placeholder="Деталі...", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        cat = discord.utils.get(guild.categories, name="🎫 ЗВЕРНЕННЯ ДО МОДЕРАЦІЇ") or await guild.create_category("🎫 ЗВЕРНЕННЯ ДО МОДЕРАЦІЇ")
        ch = await guild.create_text_channel(f"🎫-{interaction.user.name.lower()}", category=cat, overwrites={
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True)
        })
        embed = discord.Embed(title=f"🎫 {self.subject.value}", description=f"**Автор:** {interaction.user.mention}\n**Опис:** {self.details.value}", color=discord.Color.blurple())
        await ch.send(interaction.user.mention, embed=embed, view=ModernTicketControlView(interaction.user.id))
        await interaction.followup.send(f"✅ Тікет створено -> {ch.mention}", ephemeral=True)

class ModernTicketView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Створити тікет", style=discord.ButtonStyle.success, emoji="🎫", custom_id="mk_ticket")
    async def mk(self, i, b): await i.response.send_modal(ModernTicketModal())

class ModernTicketControlView(discord.ui.View):
    def __init__(self, author_id): super().__init__(timeout=None); self.author_id, self.mod_id = author_id, None

    @discord.ui.button(label="📌 Взяти на розгляд", style=discord.ButtonStyle.primary, custom_id="take_t")
    async def take(self, interaction, button):
        if not is_staff_or_admin(interaction.user): return await interaction.response.send_message("❌ Немає прав!", ephemeral=True)
        self.mod_id = interaction.user.id
        button.disabled = True
        await interaction.message.edit(view=self)
        await interaction.channel.send(f"📌 Тікет узяв {interaction.user.mention}.")

    @discord.ui.button(label="🔒 Закрити тікет", style=discord.ButtonStyle.danger, custom_id="close_t")
    async def close(self, interaction, button):
        if not is_staff_or_admin(interaction.user) and interaction.user.id != self.author_id:
            return await interaction.response.send_message("❌ Немає прав!", ephemeral=True)
        await interaction.response.send_message(embed=discord.Embed(title="⭐ Оцініть роботу модератора", color=discord.Color.blurple()), view=TicketRatingView(interaction.guild.id, self.mod_id, self.author_id, interaction.channel))

# ==================== УНИВЕРСАЛЬНАЯ КОМАНДА СЕТАПА ====================

@bot.tree.command(name="setup_forum", description="Створити панель скарг у вказаному форумі чи каналі")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(channel="Виберіть форум або канал, куди надіслати панель скарг")
async def setup_forum(interaction: discord.Interaction, channel: discord.abc.GuildChannel):
    embed = discord.Embed(
        title=f"📋 Скарги ({channel.name})",
        description=(
            "❓ У цьому каналі ви можете створити скаргу.\n"
            "Щоб подати скаргу, натисніть кнопку нижче.\n\n"
            "1. **Вимоги до скарг:**\n"
            "• Чіткі докази (відео/скріншоти)\n"
            "• Опис суті ситуації\n"
            "• Коректні нікнейми\n\n"
            "2. Подається тільки учасником ситуації в адекватній формі."
        ),
        color=discord.Color.red()
    )
    
    try:
        # Проверяем, является ли выбранный канал Форумом
        if isinstance(channel, discord.ForumChannel):
            thread = await channel.create_thread(
                name=f"📌 | Скарги ({channel.name})",
                embed=embed,
                view=CreateComplaintView()
            )
            await interaction.response.send_message(f"✅ Ветку с панелью жалоба успешно создано в форуме {channel.mention} -> {thread.thread.mention}!", ephemeral=True)
        else:
            await channel.send(embed=embed, view=CreateComplaintView())
            await interaction.response.send_message(f"✅ Панель успішно надіслано в канал {channel.mention}!", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Помилка надсилання: {e}", ephemeral=True)

@bot.tree.command(name="ticketpanel", description="Створити панель тікетів")
@app_commands.default_permissions(administrator=True)
async def ticketpanel(interaction: discord.Interaction):
    await interaction.channel.send(embed=discord.Embed(title="🛡️ Звернення до Модерації", description="Натисніть кнопку нижче, щоб відкрити тікет.", color=discord.Color.blurple()), view=ModernTicketView())
    await interaction.response.send_message("✅ Панель тікетів створена!", ephemeral=True)

@bot.tree.command(name="ban", description="Бан")
@app_commands.default_permissions(ban_members=True)
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "Не вказано"):
    if not is_staff_or_admin(interaction.user): return await interaction.response.send_message("❌ Немає прав!", ephemeral=True)
    await member.ban(reason=reason)
    add_mod_stat(interaction.guild.id, interaction.user.id)
    await interaction.response.send_message(f"🔨 Заблоковано {member.mention}.")
    await send_mod_log(interaction.guild, f"🔨 **БАН** | {member.mention} | Адмін: {interaction.user.mention} | Причина: {reason}")

@bot.tree.command(name="mute", description="Мут")
@app_commands.default_permissions(moderate_members=True)
async def mute(interaction: discord.Interaction, member: discord.Member, minutes: int, reason: str = "Не вказано"):
    if not is_staff_or_admin(interaction.user): return await interaction.response.send_message("❌ Немає прав!", ephemeral=True)
    await member.timeout(timedelta(minutes=minutes), reason=reason)
    add_mod_stat(interaction.guild.id, interaction.user.id)
    await interaction.response.send_message(f"🔇 Мут {member.mention} на {minutes} хв.")
    await send_mod_log(interaction.guild, f"🔇 **МУТ** | {member.mention} | Час: {minutes} хв | Причина: {reason}", discord.Color.gold())

@bot.tree.command(name="warn", description="Варн")
@app_commands.default_permissions(moderate_members=True)
async def warn(interaction: discord.Interaction, member: discord.Member, reason: str = "Не вказано"):
    if not is_staff_or_admin(interaction.user): return await interaction.response.send_message("❌ Немає прав!", ephemeral=True)
    cursor.execute("INSERT INTO warns (guild_id, user_id, warn_count) VALUES (?, ?, 1) ON CONFLICT(guild_id, user_id) DO UPDATE SET warn_count = warn_count + 1", (interaction.guild.id, member.id))
    db.commit()
    cursor.execute("SELECT warn_count FROM warns WHERE guild_id = ? AND user_id = ?", (interaction.guild.id, member.id))
    warns = cursor.fetchone()[0]
    add_mod_stat(interaction.guild.id, interaction.user.id)
    await interaction.response.send_message(f"⚠️ Варн {member.mention} [{warns}/3].")
    await send_mod_log(interaction.guild, f"⚠️ **ВАРН** | {member.mention} [{warns}/3] | Причина: {reason}", discord.Color.orange())

bot.run(os.getenv('TOKEN'))
