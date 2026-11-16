import os
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from google import genai

# Завантажуємо змінні середовища з файлу .env
load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

warnings_db = {}

# Ініціалізація клієнта Gemini з актуальною моделлю
gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


@bot.event
async def on_ready():
  print(f"Бот {bot.user} успішно запущений і готовий до роботи!")
  try:
    synced = await bot.tree.sync()
    print(f"Синхронізовано слеш-команд: {len(synced)}")
  except Exception as e:
    print(e)


# ==========================================
# 1. КОМАНДА ПИСАТИ ВІД ІМЕНІ БОТА (/say)
# ==========================================


@bot.tree.command(
    name="say", description="Написати повідомлення від імені бота у вказаний канал"
)
@app_commands.default_permissions(administrator=True)
async def say(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    *,
    text: str,
):
  await channel.send(text)
  await interaction.response.send_message(
      f"✅ Повідомлення успішно надіслано в канал {channel.mention}!",
      ephemeral=True,
  )


# ==========================================
# 2. СИСТЕМА ТІКЕТІВ З КНОПКАМИ ТА ОЦІНКОЮ
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

    channel_name = f"тікет-{interaction.user.name}"
    ticket_channel = await guild.create_text_channel(
        channel_name, overwrites=overwrites
    )

    manage_view = TicketManageView()
    await ticket_channel.send(
        f"Вітаю, {interaction.user.mention}! Опишіть вашу проблему."
        " Модерація скоро відповість.",
        view=manage_view,
    )
    await interaction.response.send_message(
        f"Ваш тікет успішно створено: {ticket_channel.mention}!", ephemeral=True
    )


class TicketFeedbackView(discord.ui.View):
  """Меню оцінки роботи модератора після закриття тікета"""

  def __init__(self, ticket_author: discord.Member, channel_name: str):
    super().__init__(timeout=60)
    self.ticket_author = ticket_author
    self.channel_name = channel_name

  async def send_log_to_dm(self, rating: str, interaction: discord.Interaction):
    embed = discord.Embed(
        title="🔒 Закритий тікет — Звіт та Оцінка",
        color=discord.Color.blurple(),
    )
    embed.add_field(name="📁 Назва тікета", value=self.channel_name, inline=False)
    embed.add_field(name="👤 Створив", value=self.ticket_author.mention, inline=True)
    embed.add_field(name="⭐ Оцінка", value=rating, inline=True)
    embed.set_footer(text="Архів логів безпеки Varta UA")

    # Надсилаємо гравцю в ЛС
    try:
      await self.ticket_author.send(embed=embed)
    except Exception:
      pass

    # Надсилаємо модератору, який закрив, у ЛС
    try:
      await interaction.user.send(embed=embed)
    except Exception:
      pass

  @discord.ui.button(label="Відмінно ⭐", style=discord.ButtonStyle.green, custom_id="rate_5")
  async def rate_great(self, interaction: discord.Interaction, button: discord.ui.Button):
    await self.send_log_to_dm("Відмінно ⭐", interaction)
    await interaction.response.send_message("Дякуємо за оцінку! Канал буде видалено.", ephemeral=True)
    await interaction.channel.delete()

  @discord.ui.button(label="Середньо ⚡", style=discord.ButtonStyle.blurple, custom_id="rate_3")
  async def rate_mid(self, interaction: discord.Interaction, button: discord.ui.Button):
    await self.send_log_to_dm("Середньо ⚡", interaction)
    await interaction.response.send_message("Дякуємо за відгук! Канал буде видалено.", ephemeral=True)
    await interaction.channel.delete()

  @discord.ui.button(label="Погано ❌", style=discord.ButtonStyle.red, custom_id="rate_1")
  async def rate_bad(self, interaction: discord.Interaction, button: discord.ui.Button):
    await self.send_log_to_dm("Погано ❌", interaction)
    await interaction.response.send_message("Дякуємо за відгук! Канал буде видалено.", ephemeral=True)
    await interaction.channel.delete()


class TicketManageView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=None)

  @discord.ui.button(
      label="Взяти тікет",
      style=discord.ButtonStyle.green,
      custom_id="claim_ticket",
      emoji="🙋‍♂️",
  )
  async def claim_ticket(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    await interaction.response.send_message(
        f"✅ Тікет взяв у роботу модератор: {interaction.user.mention}"
    )

  @discord.ui.button(
      label="Передати модератору",
      style=discord.ButtonStyle.blurple,
      custom_id="transfer_mod",
      emoji="🛡️",
  )
  async def transfer_mod(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    role = discord.utils.get(interaction.guild.roles, name="Команда Модерації (Discord)")
    role_mention = role.mention if role else "@Команда Модерації (Discord)"
    await interaction.response.send_message(
        f"📢 Тікет передано до складу модерації: {role_mention}"
    )

  @discord.ui.button(
      label="Передати Discord Manager",
      style=discord.ButtonStyle.grey,
      custom_id="transfer_higher_mod",
      emoji="⭐",
  )
  async def transfer_higher_mod(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    role = discord.utils.get(interaction.guild.roles, name="Discord Manager")
    role_mention = role.mention if role else "@Discord Manager"
    await interaction.response.send_message(
        f"🚨 Тікет передано вищому керівництву: {role_mention}"
    )

  @discord.ui.button(
      label="Закрити тікет",
      style=discord.ButtonStyle.red,
      custom_id="close_ticket",
      emoji="🔒",
  )
  async def close_ticket(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    # Шукаємо автора тікета за назвою каналу або беремо interaction.user для прикладу
    feedback_view = TicketFeedbackView(ticket_author=interaction.user, channel_name=interaction.channel.name)
    await interaction.response.send_message(
        "🔒 **Тікет закрито.** Оберіть оцінку роботи модерації нижче:",
        view=feedback_view,
        ephemeral=False
    )


@bot.tree.command(
    name="setup_tickets", description="Надіслати панель створення тікетів у канал"
)
@app_commands.default_permissions(administrator=True)
async def setup_tickets(interaction: discord.Interaction):
  embed = discord.Embed(
      title="🎟️ Система підтримки та тікетів",
      description=(
          "Натисніть кнопку нижче, щоб відкрити приватний тікет із модерацією."
      ),
      color=discord.Color.blurple(),
  )
  await interaction.channel.send(embed=embed, view=TicketView())
  await interaction.response.send_message(
      "Панель тікетів надіслано в цей канал!", ephemeral=True
  )


# ==========================================
# 3. ДОПОМІЖНА ФУНКЦІЯ ЛОГУВАННЯ ПОКАРАНЬ
# ==========================================

async def send_punishment_log(guild: discord.Guild, text: str):
  """Надсилає лог покарання у канал 'видача-покарань'"""
  for channel in guild.text_channels:
    if "видача-покарань" in channel.name.lower():
      try:
        await channel.send(text)
        break
      except Exception:
        pass


# ==========================================
# 4. ВИКЛИК МОДЕРАЦІЇ (/report у чаті)
# ==========================================


@bot.tree.command(
    name="report", description="Екстрено викликати модерацію через порушення"
)
async def report(interaction: discord.Interaction, *, reason: str):
  await interaction.response.send_message(
      "✅ Виклик модераторів успішно надіслано!", ephemeral=True
  )

  embed = discord.Embed(
      title="🚨 Екстрений виклик модерації", color=discord.Color.red()
  )
  embed.add_field(
      name="Хто викликав", value=interaction.user.mention, inline=True
  )
  embed.add_field(
      name="Поточний канал", value=interaction.channel.mention, inline=True
  )
  embed.add_field(name="Причина / Ситуація", value=reason, inline=False)
  embed.set_footer(text="Модератори отримали сповіщення.")

  role = discord.utils.get(interaction.guild.roles, name="Команда Модерації (Discord)")
  role_mention = role.mention if role else "@Команда Модерації (Discord)"

  await interaction.channel.send(
      f"{role_mention} Увага, зафіксовано виклик модерації!", embed=embed
  )


# ==========================================
# 5. КОМАНДИ МОДЕРАЦІЇ З ЛОГАМИ
# ==========================================


@bot.tree.command(name="ban", description="Забанити учасника на сервері")
@app_commands.default_permissions(ban_members=True)
async def ban(
    interaction: discord.Interaction,
    member: discord.Member,
    *,
    reason: str = "Причина не вказана",
):
  try:
    await member.ban(reason=reason)
    await interaction.response.send_message(
        f"✅ Користувача {member.mention} успішно забанено.", ephemeral=True
    )
    log_text = f"🔨 Модератор {interaction.user.mention} забанив {member.mention}.\n📝 **Причина:** {reason}"
    await send_punishment_log(interaction.guild, log_text)
  except Exception as e:
    await interaction.response.send_message(
        f"❌ Не вдалося забанити гравця: `{e}`", ephemeral=True
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
      f"🔇 Учаснику {member.mention} видано мут на {minutes} хв.", ephemeral=True
  )
  log_text = f"🔨 Модератор {interaction.user.mention} замутив {member.mention} на **{minutes} хв.**\n📝 **Причина:** {reason}"
  await send_punishment_log(interaction.guild, log_text)


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
      f"⚠️ Учаснику {member.mention} видано попередження (всього: {count}).", ephemeral=True
  )
  log_text = f"⚠️ Модератор {interaction.user.mention} видав попередження гравцю {member.mention} (Всього: {count}).\n📝 **Причина:** {reason}"
  await send_punishment_log(interaction.guild, log_text)


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
# 6. AI АГЕНТ (GEMINI)
# ==========================================


@bot.tree.command(
    name="ai", description="Поставити запитання штучному інтелекту Gemini"
)
async def ai_chat(interaction: discord.Interaction, *, prompt: str):
  await interaction.response.defer()

  try:
    response = gemini_client.models.generate_content(
        model="gemini-3.8-flash",
        contents=prompt,
    )

    reply_text = response.text
    if len(reply_text) > 2000:
      reply_text = reply_text[:1997] + "..."

    await interaction.followup.send(f"🤖 **Питання:** {prompt}\n\n{reply_text}")

  except Exception as e:
    await interaction.followup.send(
        f"❌ Помилка AI: `{e}`\nСпробуйте написати запит іще раз."
    )


# Запуск бота
TOKEN = os.getenv("DISCORD_TOKEN")
if TOKEN:
  bot.run(TOKEN)
else:
  print("ПОМИЛКА: Не знайдено токен Discord!")
