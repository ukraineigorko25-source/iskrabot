import os
import re
import io
import sqlite3
import asyncio
from datetime import timedelta
import discord
from discord import app_commands
from discord.ext import commands
from aiohttp import web

DEVELOPER_ID = 824368499559497768

# Розширена система адміністративних ролей для 01 сервера
STAFF_ROLE_NAMES = [
    "Власник",
    "Керівник проєкту",
    "Спеціальний адміністратор",
    "Технічний адміністратор",
    "Резерв",
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

bot = commands.Bot(command_prefix="!", intents=intents)

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

def add_mod_stat(guild_id: int, moderator_id: int, rating: int = 0):
    cursor.execute("SELECT closed_count, total_rating, rating_count FROM mod_stats WHERE guild_id = ? AND moderator_id = ?", (guild_id, moderator_id))
    row = cursor.fetchone()
    
    if row:
        closed = row[0] + 1
        t_rating = row[1] + rating
        r_count = row[2] + (1 if rating > 0 else 0)
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

# ==================== ОЦІНКА ТА УПРАВЛІННЯ ТІКЕТАМИ ====================

class RatingDropdown(discord.ui.Select):
    def __init__(self, guild_id: int, moderator_id: int, author_id: int, channel: discord.TextChannel):
        self.guild_id = guild_id
        self.moderator_id = moderator_id
        self.author_id = author_id
        self.channel = channel

        options = [
            discord.SelectOption(label="Відмінно", emoji="😁", value="5", description="Чудова робота"),
            discord.SelectOption(label="Добре", emoji="🙂", value="4", description="Задовільна допомога"),
            discord.SelectOption(label="Погано", emoji="🙁", value="2", description="Проблема не була вирішена")
        ]
        super().__init__(placeholder="Оберіть оцінку...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Тільки автор тікета може оцінити роботу!", ephemeral=True)
            return

        await interaction.response.defer()
        rating_val = int(self.values[0])
        rating_text = "Відмінно" if rating_val == 5 else ("Добре" if rating_val == 4 else "Погано")

        if self.moderator_id:
            add_mod_stat(self.guild_id, self.moderator_id, rating=rating_val)

        embed = discord.Embed(
            title="🔒 Тікет закрито",
            description=f"Тікет закрито. Оцінка модератора: **\"{rating_text}\"**",
            color=discord.Color.dark_theme()
        )
        embed.set_footer(text=f"Сьогодні о {discord.utils.utcnow().strftime('%H:%M')}")
        await interaction.message.edit(content=None, embed=embed, view=None)

        messages = []
        async for msg in self.channel.history(limit=500, oldest_first=True):
            time_str = msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
            messages.append(f"<p><b>[{time_str}] {msg.author.name}:</b> {msg.content}</p>")
            
        html_content = f"<html><head><meta charset='utf-8'><title>{self.channel.name}</title></head><body style='background:#121212;color:#eee;font-family:sans-serif;'><h2>Транскрипт {self.channel.name}</h2>{''.join(messages)}</body></html>"
        file_data = io.BytesIO(html_content.encode("utf-8"))

        dm_embed = discord.Embed(
            title="🛸 Сповіщення",
            description=f"Тікет \"**{self.channel.name}**\" закритий. Ваша оцінка: **{rating_text}**.",
            color=discord.Color.blurple()
        )

        author = interaction.guild.get_member(self.author_id)
        if author:
            try:
                file_data.seek(0)
                await author.send(embed=dm_embed, file=discord.File(file_data, filename=f"{self.channel.name}.html"))
            except Exception:
                pass

        await asyncio.sleep(3)
        try:
            await self.channel.delete()
        except Exception:
            pass

class ModernTicketControlView(discord.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=None)
        self.author_id = author_id
        self.assigned_mod_id = None
        self.taken_by_anyone = False

    @discord.ui.button(label="📌 Взяти на розгляд", style=discord.ButtonStyle.primary, custom_id="modern_take_ticket_btn_v7")
    async def take_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff_or_admin(interaction.user):
            await interaction.response.send_message("❌ Недостатньо прав!", ephemeral=True)
            return
        
        if self.taken_by_anyone:
            await interaction.response.send_message("❌ Цей тікет вже взято на розгляд!", ephemeral=True)
            return

        self.taken_by_anyone = True
        self.assigned_mod_id = interaction.user.id
        button.disabled = True
        await interaction.response.edit_message(view=self)
        await interaction.channel.send(f"🛠️ Модератор {interaction.user.mention} взяв цей тікет на розгляд!")

    @discord.ui.button(label="🔒 Закрити тікет", style=discord.ButtonStyle.danger, custom_id="modern_close_ticket_btn_v7")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff_or_admin(interaction.user) and interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ У вас немає прав для закриття цього тікета!", ephemeral=True)
            return

        view = discord.ui.View()
        view.add_item(RatingDropdown(interaction.guild.id, self.assigned_mod_id, self.author_id, interaction.channel))
        await interaction.response.send_message("💚 Оцініть роботу модерації перед закриттям:", view=view)

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
        
        embed = discord.Embed(title=f"🎫 Звернення: {self.subject.value}", description=f"**Користувач:** {interaction.user.mention}\n**Опис:** {self.details.value}", color=discord.Color.blurple())
        await ticket_channel.send(embed=embed, view=ModernTicketControlView(interaction.user.id))
        await interaction.followup.send(f"✅ Тікет створено -> {ticket_channel.mention}", ephemeral=True)

class ModernTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Створити тікет", style=discord.ButtonStyle.success, emoji="🎫", custom_id="modern_create_ticket_btn_v7")
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ModernTicketModal())

# ==================== СИСТЕМА СКАРГ ТА ФОРУМІВ ====================

class ComplaintModal(discord.ui.Modal):
    def __init__(self, complaint_type: str):
        super().__init__(title=f"Скарга: {complaint_type}")
        self.complaint_type = complaint_type

    offender = discord.ui.TextInput(label="Нікнейм або ID порушника", placeholder="Приклад: User#1234 / ID", required=True)
    reason = discord.ui.TextInput(label="Суть порушення", style=discord.TextStyle.paragraph, placeholder="Опишіть ситуацію...", required=True)
    proofs = discord.ui.TextInput(label="Докази (посилання/Imgur/YouTube)", placeholder="https://...", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild

        target_channel = None
        
        # Визначаємо канал в залежності від типу скарги
        if "Адміністраці" in self.complaint_type or "Модераці" in self.complaint_type:
            for ch in guild.channels:
                if "скарги-на-адм" in ch.name.lower() or "скарги-адмін" in ch.name.lower():
                    target_channel = ch
                    break
        else:
            for ch in guild.channels:
                if "скарги-на-гравців" in ch.name.lower() or "скарги-гравці" in ch.name.lower() or "скарги" in ch.name.lower():
                    target_channel = ch
                    break
        
        if not target_channel:
            target_channel = interaction.channel

        embed = discord.Embed(
            title=f"🚨 Нова скарга: {self.complaint_type}",
            color=discord.Color.red()
        )
        embed.add_field(name="Автор скарги:", value=interaction.user.mention, inline=True)
        embed.add_field(name="Порушник:", value=self.offender.value, inline=True)
        embed.add_field(name="Причина / Опис:", value=self.reason.value, inline=False)
        embed.add_field(name="Докази:", value=self.proofs.value, inline=False)
        embed.set_footer(text=f"ID Автора: {interaction.user.id}")

        # Якщо канал є Форумом (ForumChannel)
        if isinstance(target_channel, discord.ForumChannel):
            thread, _ = await target_channel.create_thread(
                name=f"Скарга на {self.offender.value}",
                embed=embed,
                view=ComplaintControlView()
            )
            await interaction.followup.send(f"✅ Вашу скаргу опубліковано у форумі -> {thread.mention}", ephemeral=True)
        else:
            await target_channel.send(embed=embed, view=ComplaintControlView())
            await interaction.followup.send(f"✅ Вашу скаргу надіслано в канал {target_channel.mention}", ephemeral=True)

class ComplaintControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Схвалити скаргу", style=discord.ButtonStyle.success, emoji="✅", custom_id="cmp_accept_btn_v1")
    async def accept_complaint(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff_or_admin(interaction.user):
            return await interaction.response.send_message("❌ Недостатньо прав!", ephemeral=True)

        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        add_mod_stat(interaction.guild.id, interaction.user.id)
        await interaction.channel.send(f"✅ Скаргу розглянуто та схвалено модератором {interaction.user.mention}!")

    @discord.ui.button(label="Відхилити", style=discord.ButtonStyle.danger, emoji="❌", custom_id="cmp_reject_btn_v1")
    async def reject_complaint(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff_or_admin(interaction.user):
            return await interaction.response.send_message("❌ Недостатньо прав!", ephemeral=True)

        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        add_mod_stat(interaction.guild.id, interaction.user.id)
        await interaction.channel.send(f"❌ Скаргу відхилено модератором {interaction.user.mention}.")

class CreateComplaintView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Скарга на Гравця", style=discord.ButtonStyle.danger, emoji="👤", custom_id="open_player_complaint_modal")
    async def open_player_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ComplaintModal("Скарга на Гравця"))

    @discord.ui.button(label="Скарга на Адміністрацію", style=discord.ButtonStyle.secondary, emoji="🛡️", custom_id="open_admin_complaint_modal")
    async def open_admin_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ComplaintModal("Скарга на Адміністрацію"))

# ==================== ВИБІР РОЛЕЙ "ХЛОПЕЦЬ / ДІВЧИНА" ====================

class GenderSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Хлопець ♂️", style=discord.ButtonStyle.primary, custom_id="gender_male_btn_v2")
    async def set_male(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._assign_gender_role(interaction, ["Хлопець", "хлопець", "Хлопець ♂️"], ["Дівчина", "дівчина", "Дівчина ♀️"])

    @discord.ui.button(label="Дівчина ♀️", style=discord.ButtonStyle.secondary, custom_id="gender_female_btn_v2")
    async def set_female(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._assign_gender_role(interaction, ["Дівчина", "дівчина", "Дівчина ♀️"], ["Хлопець", "хлопець", "Хлопець ♂️"])

    async def _assign_gender_role(self, interaction: discord.Interaction, target_names: list, opposite_names: list):
        guild = interaction.guild
        member = interaction.user
        
        target_role = None
        for name in target_names:
            target_role = discord.utils.get(guild.roles, name=name)
            if target_role:
                break

        opposite_role = None
        for name in opposite_names:
            opposite_role = discord.utils.get(guild.roles, name=name)
            if opposite_role:
                break

        if not target_role:
            await interaction.response.send_message(f"❌ Роль не знайдено на сервері! Зверніться до адміністрації.", ephemeral=True)
            return

        try:
            if opposite_role and opposite_role in member.roles:
                await member.remove_roles(opposite_role)
            await member.add_roles(target_role)
            await interaction.response.send_message(f"✅ Вам успішно видано роль **{target_role.name}**!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Помилка видачі ролі: {e}", ephemeral=True)

# ==================== СИСТЕМА ЗАЯВОК ТА ФРАКЦІЙ ====================

class FactionModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="Заявка на фракцію / роль")

    nickname = discord.ui.TextInput(label="Ваш нікнейм та static ID", placeholder="Іван Іванов [1234]", required=True)
    faction = discord.ui.TextInput(label="Яка роль / фракція потрібна", placeholder="Хлопець / Дівчина / Назва фракції", required=True)
    comment = discord.ui.TextInput(label="Коментар або скріншот", style=discord.TextStyle.paragraph, placeholder="Додаткова інформація...", required=False)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild

        target_channel = None
        for ch in guild.text_channels:
            if any(k in ch.name.lower() for k in ["заявки", "заявки-гравців", "заявки-фракції", "перевірка"]):
                target_channel = ch
                break

        if not target_channel:
            target_channel = interaction.channel

        embed = discord.Embed(
            title="📥 Нова заявка на отримання ролі",
            color=discord.Color.gold()
        )
        embed.add_field(name="Гравець:", value=interaction.user.mention, inline=True)
        embed.add_field(name="Нікнейм / ID:", value=self.nickname.value, inline=True)
        embed.add_field(name="Бажана роль/фракція:", value=self.faction.value, inline=False)
        if self.comment.value:
            embed.add_field(name="Коментар:", value=self.comment.value, inline=False)
        embed.set_footer(text=f"ID користувача: {interaction.user.id}")

        await target_channel.send(embed=embed, view=FactionAppControlView(interaction.user.id, self.faction.value))
        await interaction.followup.send(f"✅ Вашу заявку відправлено у канал {target_channel.mention}!", ephemeral=True)

class FactionAppControlView(discord.ui.View):
    def __init__(self, applicant_id: int, faction_name: str):
        super().__init__(timeout=None)
        self.applicant_id = applicant_id
        self.faction_name = faction_name

    @discord.ui.button(label="Схвалити", style=discord.ButtonStyle.success, emoji="✅", custom_id="f_acc_v2")
    async def accept_app(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff_or_admin(interaction.user):
            return await interaction.response.send_message("❌ Недостатньо прав!", ephemeral=True)

        applicant = interaction.guild.get_member(self.applicant_id)
        role = discord.utils.get(interaction.guild.roles, name=self.faction_name)
        
        if applicant and role:
            try:
                await applicant.add_roles(role)
            except Exception:
                pass

        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        add_mod_stat(interaction.guild.id, interaction.user.id)
        await interaction.channel.send(f"✅ Заявку схвалив {interaction.user.mention}. Роль видано!")

    @discord.ui.button(label="Відхилити", style=discord.ButtonStyle.danger, emoji="❌", custom_id="f_rej_v2")
    async def reject_app(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff_or_admin(interaction.user):
            return await interaction.response.send_message("❌ Недостатньо прав!", ephemeral=True)

        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        add_mod_stat(interaction.guild.id, interaction.user.id)
        await interaction.channel.send(f"❌ Заявку відхилив {interaction.user.mention}.")

class FactionPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Подати заявку", style=discord.ButtonStyle.primary, emoji="📋", custom_id="f_panel_btn_v2")
    async def open_faction_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(FactionModal())

# ==================== СЛАШ-КОМАНДИ МОДЕРАЦІЇ ТА ПАНЕЛЕЙ ====================

@bot.tree.command(name="ticket_panel", description="Надіслати панель створення тікетів")
@app_commands.default_permissions(administrator=True)
async def ticket_panel(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🎫 Центр підтримки користувачів",
        description="Якщо у вас виникли запитання або вам потрібна допомога модерації, натисніть кнопку нижче, щоб створити тікет.",
        color=discord.Color.blurple()
    )
    await interaction.channel.send(embed=embed, view=ModernTicketView())
    await interaction.response.send_message("✅ Панель тікетів опубліковано!", ephemeral=True)

@bot.tree.command(name="complaint_panel", description="Надіслати панель подачі скарг")
@app_commands.default_permissions(administrator=True)
async def complaint_panel(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🚨 Подача скарг",
        description="Оберіть відповідну кнопку нижче, щоб подати скаргу на порушника або члена адміністрації.",
        color=discord.Color.red()
    )
    await interaction.channel.send(embed=embed, view=CreateComplaintView())
    await interaction.response.send_message("✅ Панель скарг опубліковано!", ephemeral=True)

@bot.tree.command(name="gender_panel", description="Надіслати панель вибору ролі (Хлопець/Дівчина)")
@app_commands.default_permissions(administrator=True)
async def gender_panel(interaction: discord.Interaction):
    embed = discord.Embed(
        title="👥 Вибір гендерної ролі",
        description="Оберіть кнопку відповідно до вашої статі для отримання ролі на сервері.",
        color=discord.Color.green()
    )
    await interaction.channel.send(embed=embed, view=GenderSelectView())
    await interaction.response.send_message("✅ Панель гендерних ролей опубліковано!", ephemeral=True)

@bot.tree.command(name="faction_panel", description="Надіслати панель заявок на фракції та ролі")
@app_commands.default_permissions(administrator=True)
async def faction_panel(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📋 Заявки на отримання ролей / фракцій",
        description="Натисніть кнопку нижче, щоб подати заявку на отримання ролі фракції або організації.",
        color=discord.Color.gold()
    )
    await interaction.channel.send(embed=embed, view=FactionPanelView())
    await interaction.response.send_message("✅ Панель заявок опубліковано!", ephemeral=True)

@bot.tree.command(name="warn", description="Видати попередження (варн) користувачу")
@app_commands.describe(member="Користувач", reason="Причина попередження")
async def warn(interaction: discord.Interaction, member: discord.Member, reason: str = "Порушення правил"):
    if not is_staff_or_admin(interaction.user):
        return await interaction.response.send_message("❌ У вас немає прав!", ephemeral=True)

    cursor.execute("SELECT warn_count FROM warns WHERE guild_id = ? AND user_id = ?", (interaction.guild.id, member.id))
    row = cursor.fetchone()
    current_warns = (row[0] + 1) if row else 1

    if row:
        cursor.execute("UPDATE warns SET warn_count = ? WHERE guild_id = ? AND user_id = ?", (current_warns, interaction.guild.id, member.id))
    else:
        cursor.execute("INSERT INTO warns (guild_id, user_id, warn_count) VALUES (?, ?, 1)", (interaction.guild.id, member.id))
    db.commit()

    embed = discord.Embed(
        title="⚠️ Видано попередження",
        description=f"**Модератор:** {interaction.user.mention}\n**Порушник:** {member.mention}\n**Причина:** {reason}\n**Варнів:** {current_warns}/3",
        color=discord.Color.orange()
    )
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="unwarn", description="Зняти попередження з користувача")
@app_commands.describe(member="Користувач")
async def unwarn(interaction: discord.Interaction, member: discord.Member):
    if not is_staff_or_admin(interaction.user):
        return await interaction.response.send_message("❌ У вас немає прав!", ephemeral=True)

    cursor.execute("SELECT warn_count FROM warns WHERE guild_id = ? AND user_id = ?", (interaction.guild.id, member.id))
    row = cursor.fetchone()

    if not row or row[0] == 0:
        return await interaction.response.send_message("❌ У цього користувача немає попереджень!", ephemeral=True)

    new_warns = row[0] - 1
    cursor.execute("UPDATE warns SET warn_count = ? WHERE guild_id = ? AND user_id = ?", (new_warns, interaction.guild.id, member.id))
    db.commit()

    await interaction.response.send_message(f"✅ Знято 1 варн з {member.mention}. Поточна кількість: {new_warns}/3")

@bot.tree.command(name="warns", description="Перевірити варни користувача")
@app_commands.describe(member="Користувач")
async def warns(interaction: discord.Interaction, member: discord.Member):
    cursor.execute("SELECT warn_count FROM warns WHERE guild_id = ? AND user_id = ?", (interaction.guild.id, member.id))
    row = cursor.fetchone()
    count = row[0] if row else 0
    await interaction.response.send_message(f"📊 У користувача {member.mention} кількість варнів: **{count}/3**")

@bot.tree.command(name="mute", description="Замутити користувача (Timeout)")
@app_commands.describe(member="Користувач", minutes="Хвилини", reason="Причина")
async def mute(interaction: discord.Interaction, member: discord.Member, minutes: int, reason: str = "Порушення правил"):
    if not is_staff_or_admin(interaction.user):
        return await interaction.response.send_message("❌ У вас немає прав!", ephemeral=True)

    duration = timedelta(minutes=minutes)
    try:
        await member.timeout(duration, reason=reason)
        await interaction.response.send_message(f"🔇 Користувача {member.mention} замучено на {minutes} хв. Причина: {reason}")
    except Exception as e:
        await interaction.response.send_message(f"❌ Не вдалося замутити користувача: {e}", ephemeral=True)

@bot.tree.command(name="unmute", description="Зняти мут з користувача")
@app_commands.describe(member="Користувач")
async def unmute(interaction: discord.Interaction, member: discord.Member):
    if not is_staff_or_admin(interaction.user):
        return await interaction.response.send_message("❌ У вас немає прав!", ephemeral=True)

    try:
        await member.timeout(None)
        await interaction.response.send_message(f"🔊 З користувача {member.mention} знято мут.")
    except Exception as e:
        await interaction.response.send_message(f"❌ Помилка зняття муту: {e}", ephemeral=True)

@bot.tree.command(name="clear", description="Очистити повідомлення у чаті")
@app_commands.describe(amount="Кількість повідомлень")
async def clear(interaction: discord.Interaction, amount: int):
    if not is_staff_or_admin(interaction.user):
        return await interaction.response.send_message("❌ У вас немає прав!", ephemeral=True)

    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.followup.send(f"🧹 Видалено {len(deleted)} повідомлень!", ephemeral=True)

@bot.tree.command(name="stats", description="Переглянути статистику модератора")
@app_commands.describe(member="Модератор")
async def stats(interaction: discord.Interaction, member: discord.Member = None):
    target = member or interaction.user
    cursor.execute("SELECT closed_count, total_rating, rating_count FROM mod_stats WHERE guild_id = ? AND moderator_id = ?", (interaction.guild.id, target.id))
    row = cursor.fetchone()

    if not row:
        return await interaction.response.send_message(f"📊 Модератор {target.mention} ще не закрив жодного тікета.", ephemeral=True)

    closed, total_rating, rating_count = row
    avg_rating = round(total_rating / rating_count, 1) if rating_count > 0 else 0.0

    embed = discord.Embed(title=f"📊 Статистика модератора {target.display_name}", color=discord.Color.blue())
    embed.add_field(name="Закрито тікетів/скарг:", value=str(closed), inline=True)
    embed.add_field(name="Середня оцінка:", value=f"⭐ {avg_rating}/5", inline=True)
    await interaction.response.send_message(embed=embed)

# ==================== ЗАПУСК БОТА ТА ВЕБ-СЕРВЕРА ====================

@bot.event
async def on_ready():
    # Реєстрація персистентних View
    bot.add_view(ModernTicketView())
    bot.add_view(CreateComplaintView())
    bot.add_view(GenderSelectView())
    bot.add_view(FactionPanelView())

    # Синхронізація слаш-команд
    try:
        synced = await bot.tree.sync()
        print(f"✅ Синхронізовано {len(synced)} слаш-команд.")
    except Exception as e:
        print(f"❌ Помилка синхронізації команд: {e}")

    print(f"🤖 Бот успішно запущений як {bot.user}")

async def handle_ping(request):
    return web.Response(text="Bot is running 24/7!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"🌐 Веб-сервер запущено на порту {port}")

async def main():
    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        print("❌ Помилка: Змінну DISCORD_TOKEN не знайдено!")
        return

    await start_web_server()
    async with bot:
        await bot.start(token)

if __name__ == "__main__":
    asyncio.run(main())
