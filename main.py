import os
import discord
from discord.ext import commands
from discord import app_commands

# Налаштування інтентів
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Бот {bot.user} успішно запущено!")
    try:
        synced = await bot.tree.sync()
        print(f"Синхронізовано слеш-команд: {len(synced)}")
    except Exception as e:
        print(e)


# ==========================================
# 1. СИСТЕМА МОДЕРАЦІЇ
# ==========================================

@bot.tree.command(name="kick", description="Вигнати учасника з сервера")
@app_commands.default_permissions(kick_members=True)
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "Причина не вказана"):
    await member.kick(reason=reason)
    await interaction.response.send_message(f"Успішно вигнано {member.mention}. Причина: {reason}", ephemeral=True)

@bot.tree.command(name="ban", description="Забанити учасника на сервері")
@app_commands.default_permissions(ban_members=True)
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "Причина не вказана"):
    await member.ban(reason=reason)
    await interaction.response.send_message(f"Успішно забанено {member.mention}. Причина: {reason}", ephemeral=True)

@bot.tree.command(name="timeout", description="Замутити учасника на певний час (хвилини)")
@app_commands.default_permissions(moderate_members=True)
async def timeout(interaction: discord.Interaction, member: discord.Member, minutes: int, reason: str = "Причина не вказана"):
    duration = discord.utils.utcnow() + discord.timedelta(minutes=minutes)
    await member.timeout(duration, reason=reason)
    await interaction.response.send_message(f"Учасника {member.mention} замучено на {minutes} хв. Причина: {reason}", ephemeral=True)


# ==========================================
# 2. СИСТЕМА ТІКЕТІВ (ЧЕРЕЗ КНОПКИ)
# ==========================================

class TicketModal(discord.ui.Modal, title="Створити тікет"):
    reason = discord.ui.TextInput(
        label="Опишіть вашу проблему / питання",
        style=discord.TextStyle.long,
        placeholder="Детально розпишіть ситуацію...",
        required=True,
        max_length=300,
    )

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        # Шукаємо категорію для тікетів (можна змінити назву)
        category = discord.utils.get(guild.categories, name="Тікети")
        if not category:
            category = await guild.create_category("Тікети")

        # Права доступу: тільки користувач і адміністрація бачать канал
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }

        # Додаємо роль модераторів, якщо вона є (наприклад, роль "Модератор")
        mod_role = discord.utils.get(guild.roles, name="Модератор")
        if mod_role:
            overwrites[mod_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        # Створюємо канал
        channel_name = f"ticket-{interaction.user.name}"
        ticket_channel = await guild.create_text_channel(channel_name, category=category, overwrites=overwrites)

        # Кнопка для закриття тікета
        view = CloseTicketView()
        embed = discord.Embed(
            title="Тікет створено",
            description=f"**Автор:** {interaction.user.mention}\n**Питання:** {self.reason.value}",
            color=discord.Color.green()
        )
        await ticket_channel.send(content=f"{interaction.user.mention}, адміністрація скоро вам відповість!", embed=embed, view=view)
        await interaction.response.send_message(f"Ваш тікет створено: {ticket_channel.mention}!", ephemeral=True)

class CloseTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Закрити тікет", style=discord.ButtonStyle.danger, custom_id="close_ticket_btn")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Канал буде видалено через 5 секунд...", ephemeral=True)
        await discord.utils.sleep_until(discord.utils.utcnow() + discord.timedelta(seconds=5))
        await interaction.channel.delete()

class TicketSetupView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎫 Створити тікет", style=discord.ButtonStyle.blurple, custom_id="open_ticket_btn")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TicketModal())

@bot.tree.command(name="ticket-panel", description="Викликати панель створення тікетів (тільки для адмінів)")
@app_commands.default_permissions(administrator=True)
async def ticket_panel(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Система підтримки (Тікети)",
        description="Натисніть кнопку нижче, щоб відкрити приватний тикет із адміністрацією.",
        color=discord.Color.blue()
    )
    await interaction.channel.send(embed=embed, view=TicketSetupView())
    await interaction.response.send_message("Панель тікетів успішно створено!", ephemeral=True)


# ==========================================
# 3. СИСТЕМА СКАРГ ЧЕРЕЗ ФОРУМ
# ==========================================

class ReportModal(discord.ui.Modal, title="Створити скаргу на гравця"):
    violator = discord.ui.TextInput(
        label="Нікнейм порушника / ID",
        placeholder="Наприклад: Ігор / ID 1234",
        required=True
    )
    reason_report = discord.ui.TextInput(
        label="Суть скарги та докази (силк на відео/скрін)",
        style=discord.TextStyle.long,
        placeholder="Опишіть ситуацію та прикріпіть докази (YouTube, Imgur тощо)...",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        # Шукаємо форум-канал за назвою "скарги"
        forum_channel = discord.utils.get(interaction.guild.forums, name="скарги")
        if not forum_channel:
            await interaction.response.send_message("Помилка: Форум-канал з назвою 'скарги' не знайдено на сервері!", ephemeral=True)
            return

        thread_title = f"Скарга на: {self.violator.value}"
        thread_content = f"**Скаргу подав:** {interaction.user.mention}\n**Порушник:** {self.violator.value}\n**Опис та докази:**\n{self.reason_report.value}"
        
        # Створюємо пост (гілку) у форумі
        thread = await forum_channel.create_thread(name=thread_title, content=thread_content)
        await interaction.response.send_message(f"Вашу скаргу успішно створено у форумі: {thread.thread.mention}!", ephemeral=True)

class ReportSetupView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Подати скаргу", style=discord.ButtonStyle.red, custom_id="open_report_btn")
    async def open_report(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ReportModal())

@bot.tree.command(name="report-panel", description="Створити панель подачі скарг через форум")
@app_commands.default_permissions(administrator=True)
async def report_panel(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Подати скаргу на гравця",
        description="Натисніть кнопку нижче, щоб заповнити форму скарги. Вона автоматично створить окрему гілку у форум-каналі **#скарги**.",
        color=discord.Color.dark_red()
    )
    await interaction.channel.send(embed=embed, view=ReportSetupView())
    await interaction.response.send_message("Панель скарг успішно створена!", ephemeral=True)

# Запуск бота (токен підтягується автоматично з налаштувань Wispbyte / .env)
bot.run(os.getenv("DISCORD_TOKEN"))
