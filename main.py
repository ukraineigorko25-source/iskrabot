import os
import discord
from discord import app_commands
from discord.ext import commands
from google import genai

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
# 2. СИСТЕМА ТІКЕТІВ З КНОПКАМИ
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

    close_view = TicketCloseView()
    await ticket_channel.send(
        f"Вітаю, {interaction.user.mention}! Опишіть вашу проблему."
        " Адміністрація скоро відповість.",
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
# 3. ВИКЛИК МОДЕРАЦІЇ (/report у чаті)
# ==========================================


@bot.tree.command(
    name="report",
    description="Викликати модерацію через порушення у Discord чаті",
)
async def report(
    interaction: discord.Interaction,
    member: discord.Member,
    *,
    reason: str,
):
  embed = discord.Embed(
      title="🚨 Екстрений виклик модерації", color=discord.Color.red()
  )
  embed.add_field(
      name="Хто викликав", value=interaction.user.mention, inline=True
  )
  embed.add_field(name="Порушник", value=member.mention, inline=True)
  embed.add_field(name="Причина / Ситуація", value=reason, inline=False)
  embed.set_footer(text="Модератори отримали сповіщення.")

  await interaction.channel.send(
      "@here Увага, зафіксовано репорт на порушника!", embed=embed
  )
  await interaction.response.send_message(
      "✅ Виклик модераторів успішно надіслано!", ephemeral=True
  )


# ==========================================
# 4. ПАНЕЛЬ СКАРГ У ФОРУМ (Кнопки для форумів)
# ==========================================


class ForumReportSelect(discord.ui.Select):

  def __init__(self):
    options = [
        discord.SelectOption(
            label="Скарги на гравця",
            value="гравц",
            description="Створити тему у фомумі гравців",
            emoji="👤",
        ),
        discord.SelectOption(
            label="Скарги на адміністраторів",
            value="адміністратор",
            description="Створити тему у форумі адмінів",
            emoji="🛡️",
        ),
        discord.SelectOption(
            label="Скарги на лідерів",
            value="лідер",
            description="Створити тему у форумі лідерів",
            emoji="⭐",
        ),
        discord.SelectOption(
            label="Скарги на керівництво",
            value="керівництв",
            description="Створити тему у форумі керівництва",
            emoji="👑",
        ),
    ]
    super().__init__(
        placeholder="Оберіть розділ для скарги у форум...", options=options
    )

  async def callback(self, interaction: discord.Interaction):
    modal = ForumReportModal(category_keyword=self.values[0])
    await interaction.response.send_modal(modal)


class ForumReportView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=None)
    self.add_item(ForumReportSelect())


class ForumReportModal(discord.ui.Modal, title="Форма подачі скарги у форум"):
  target_user = discord.ui.TextInput(
      label="Нік порушника / ID",
      placeholder="Наприклад: Dmytro_Collins або ID 123",
      required=True,
  )
  reason = discord.ui.TextInput(
      label="Опис ситуації та докази",
      style=discord.TextStyle.paragraph,
      placeholder="Опишіть детально та вкажіть посилання на докази...",
      required=True,
      max_length=1000,
  )

  def __init__(self, category_keyword: str):
    super().__init__()
    self.category_keyword = category_keyword

  async def on_submit(self, interaction: discord.Interaction):
    guild = interaction.guild

    forum_channel = None
    for channel in guild.channels:
      if isinstance(channel, discord.ForumChannel):
        if self.category_keyword in channel.name.lower():
          forum_channel = channel
          break

    if not forum_channel:
      for channel in guild.channels:
        if isinstance(channel, discord.ForumChannel):
          forum_channel = channel
          break

    if not forum_channel:
      await interaction.response.send_message(
          "❌ Помилка: Не знайдено жодного каналу-форуму для скарг!",
          ephemeral=True,
      )
      return

    embed = discord.Embed(title="🚨 Офіційна скарга", color=discord.Color.red())
    embed.add_field(
        name="👤 Скаргу подав", value=interaction.user.mention, inline=True
    )
    embed.add_field(
        name="🎯 Порушник / ID", value=self.target_user.value, inline=True
    )
    embed.add_field(name="📄 Суть та докази", value=self.reason.value, inline=False)

    thread_title = f"Скарги на {self.target_user.value} від {interaction.user.name}"
    if len(thread_title) > 100:
      thread_title = thread_title[:97] + "..."

    await forum_channel.create_thread(name=thread_title, embed=embed)
    await interaction.response.send_message(
        f"✅ Вашу скаргу успішно опубліковано у форум **#{forum_channel.name}**!",
        ephemeral=True,
    )


@bot.tree.command(
    name="setup_forum_report",
    description="Надіслати панель подачі скарг у форум у канал",
)
@app_commands.default_permissions(administrator=True)
async def setup_forum_report(interaction: discord.Interaction):
  embed = discord.Embed(
      title="📋 Подача скарг у форум",
      description=(
          "Оберіть у меню нижче категорію, щоб подати скаргу через форму та"
          " автоматично створити тему у відповідному форумі."
      ),
      color=discord.Color.dark_red(),
  )
  await interaction.channel.send(embed=embed, view=ForumReportView())
  await interaction.response.send_message(
      "Панель скарг на форум успішно надіслано!", ephemeral=True
  )


# ==========================================
# 5. КОМАНДИ МОДЕРАЦІЇ
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
        f"✅ Користувача {member.mention} успішно забанено. Причина: {reason}",
        ephemeral=True,
    )
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
