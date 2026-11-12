import os
import discord
from discord import app_commands
from discord.ext import commands

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Словник для збереження варнів (попереджень) гравців
warnings_db = {}


@bot.event
async def on_ready():
  print(f"Бот {bot.user} успішно запущений і готовий до роботи!")
  try:
    synced = await bot.tree.sync()
    print(f"Синхронізовано слеш-команд: {len(synced)}")
  except Exception as e:
    print(e)


# ==========================================
# 1. СИСТЕМА ТІКЕТІВ (Створення через кнопку)
# ==========================================


class TicketView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=None)

  @discord.ui.button(
      label="Створити тікет",
      style=discord.ButtonStyle.green,
      custom_id="create_ticket",
      emoji="🎟️",
  )
  async def create_ticket(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    guild = interaction.guild
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        interaction.user: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, read_message_history=True
        ),
        guild.me: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, manage_channels=True
        ),
    }

    # Створюємо приватний канал для користувача
    channel_name = f"тікет-{interaction.user.name}"
    ticket_channel = await guild.create_text_channel(
        channel_name, overwrites=overwrites
    )

    close_view = TicketCloseView()
    await ticket_channel.send(
        f"Вітаю, {interaction.user.mention}! Опишіть вашу проблему чи"
        " запитання. Адміністрація скоро відповість.",
        view=close_view,
    )
    await interaction.response.send_message(
        f"Ваш тікет успішно створено: {ticket_channel.mention}!", ephemeral=True
    )


class TicketCloseView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=None)

  @discord.ui.button(
      label="Закрити тікет",
      style=discord.ButtonStyle.red,
      custom_id="close_ticket",
      emoji="🔒",
  )
  async def close_ticket(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    await interaction.response.send_message("Канал буде видалено через 5 секунд...")
    import asyncio

    await asyncio.sleep(5)
    await interaction.channel.delete()


@bot.tree.command(
    name="setup_tickets", description="Надіслати панель створення тікетів у канал"
)
@app_commands.default_permissions(administrator=True)
async def setup_tickets(interaction: discord.Interaction):
  embed = discord.Embed(
      title="🎟️ Система підтримки та тікетів",
      description=(
          "Натисніть кнопку нижче, щоб відкрити приватний тікет із адміністрацією."
      ),
      color=discord.Color.blurple(),
  )
  await interaction.channel.send(embed=embed, view=TicketView())
  await interaction.response.send_message(
      "Панель тікетів надіслано в цей канал!", ephemeral=True
  )


# ==========================================
# 2. СИСТЕМА СКАРГ (Вибір категорії + форма)
# ==========================================


class ReportSelect(discord.ui.Select):

  def __init__(self):
    options = [
        discord.SelectOption(
            label="Скарги на гравців",
            description="Порушення правил від гравців",
            emoji="👤",
        ),
        discord.SelectOption(
            label="Скарги на адміністрацію",
            description="Питання до роботи адмінів",
            emoji="🛡️",
        ),
        discord.SelectOption(
            label="Скарги на лідерів",
            description="Порушення від лідерів фракцій",
            emoji="👑",
        ),
        discord.SelectOption(
            label="Скарги на держ. структури",
            description="Проблеми у державних організаціях",
            emoji="🏛️",
        ),
    ]
    super().__init__(
        placeholder="Оберіть категорію скарги...",
        min_values=1,
        max_values=1,
        options=options,
    )

  async def callback(self, interaction: discord.Interaction):
    modal = ReportDetailsModal(category=self.values[0])
    await interaction.response.send_modal(modal)


class ReportSelectView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=None)
    self.add_item(ReportSelect())


class ReportDetailsModal(discord.ui.Modal, title="Оформлення скарги"):
  target_user = discord.ui.TextInput(
      label="Нік порушника / ID",
      placeholder="Наприклад: Dmytro_Collins або ID 123",
      required=True,
  )
  reason = discord.ui.TextInput(
      label="Суть скарги та докази",
      style=discord.TextStyle.paragraph,
      placeholder="Опишіть ситуацію детально...",
      required=True,
      max_length=1000,
  )

  def __init__(self, category: str):
    super().__init__()
    self.category = category

  async def on_submit(self, interaction: discord.Interaction):
    embed = discord.Embed(
        title=f"🚨 Нова скарга: {self.category}", color=discord.Color.red()
    )
    embed.add_field(name="Скаргу подав", value=interaction.user.mention, inline=True)
    embed.add_field(name="Порушник", value=self.target_user.value, inline=True)
    embed.add_field(name="Опис / Докази", value=self.reason.value, inline=False)

    await interaction.response.send_message(
        "Вашу скаргу успішно надіслано на розгляд!", ephemeral=True
    )


@bot.tree.command(
    name="report", description="Надіслати скаргу через меню категорій"
)
async def report(interaction: discord.Interaction):
  view = ReportSelectView()
  await interaction.response.send_message(
      "Оберіть категорію для вашої скарги:", view=view, ephemeral=True
  )


# ==========================================
# 3. КОМАНДИ МОДЕРАЦІЇ (Бан, Мут, Варн)
# ==========================================


@bot.tree.command(name="ban", description="Забанити учасника на сервері")
@app_commands.default_permissions(ban_members=True)
async def ban(
    interaction: discord.Interaction,
    member: discord.Member,
    *,
    reason: str = "Причина не вказана",
):
  await member.ban(reason=reason)
  await interaction.response.send_message(
      f"✅ Користувача {member.mention} успішно забанено. Причина: {reason}",
      ephemeral=True,
  )


@bot.tree.command(name="mute", description="Видати тайм-аут учаснику")
@app_commands.default_permissions(moderate_members=True)
async def mute(
    interaction: discord.Interaction,
    member: discord.Member,
    minutes: int,
    *,
    reason: str = "Причина не вказана",
):
  duration = discord.utils.utcnow() + discord.timedelta(minutes=minutes)
  await member.timeout(duration, reason=reason)
  await interaction.response.send_message(
      f"🔇 Учаснику {member.mention} видано мут на {minutes} хв. Причина:"
      f" {reason}",
      ephemeral=True,
  )


@bot.tree.command(name="unmute", description="Зняти тайм-аут з учасника")
@app_commands.default_permissions(moderate_members=True)
async def unmute(interaction: discord.Interaction, member: discord.Member):
  await member.timeout(None)
  await interaction.response.send_message(
      f"🔊 Знято мут з користувача {member.mention}.", ephemeral=True
  )


@bot.tree.command(name="warn", description="Видати попередження учаснику")
@app_commands.default_permissions(kick_members=True)
async def warn(
    interaction: discord.Interaction,
    member: discord.Member,
    *,
    reason: str = "Причина не вказана",
):
  user_id = member.id
  if user_id not in warnings_db:
    warnings_db[user_id] = []
  warnings_db[user_id].append(reason)

  count = len(warnings_db[user_id])
  await interaction.response.send_message(
      f"⚠️ Учаснику {member.mention} видано попередження. Всього варнів:"
      f" {count}. Причина: {reason}",
      ephemeral=True,
  )


@bot.tree.command(name="warnlog", description="Переглянути історію варнів гравця")
@app_commands.default_permissions(kick_members=True)
async def warnlog(interaction: discord.Interaction, member: discord.Member):
  user_id = member.id
  user_warns = warnings_db.get(user_id, [])

  if not user_warns:
    await interaction.response.send_message(
        f"У користувача {member.mention} немає попереджень.", ephemeral=True
    )
    return

  desc = "\n".join(
      [f"{i+1}. {reason}" for i, reason in enumerate(user_warns)]
  )
  embed = discord.Embed(
      title=f"📜 Історія попереджень: {member.name}",
      description=desc,
      color=discord.Color.orange(),
  )
  await interaction.response.send_message(embed=embed, ephemeral=True)


# ==========================================
# 4. ФУНКЦІЯ AI АГЕНТА
# ==========================================


@bot.tree.command(
    name="ai", description="Поставити запитання AI асистенту в чаті"
)
async def ai_chat(interaction: discord.Interaction, *, prompt: str):
  await interaction.response.defer()
  ai_response = f"🤖 **AI Агент:** Отримав запит: *'{prompt}'*."
  await interaction.followup.send(ai_response)


# Запуск бота
TOKEN = os.getenv("DISCORD_TOKEN")
if TOKEN:
  bot.run(TOKEN)
else:
  print("ПОМИЛКА: Не знайдено токен у змінних середовища DISCORD_TOKEN!")
