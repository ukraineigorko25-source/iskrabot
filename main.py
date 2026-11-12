import os
import discord
from discord import app_commands
from discord.ext import commands

# Ініціалізація бота з усіма необхідними інтентами
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
  print(f"Бот {bot.user} успішно запущений і готовий до роботи!")
  try:
    synced = await bot.tree.sync()
    print(f"Синхронізовано слеш-команд: {len(synced)}")
  except Exception as e:
    print(e)


# ==========================================
# 1. СИСТЕМА СКАРГ (Модальне вікно /report)
# ==========================================


class ReportModal(discord.ui.Modal, title="Надіслати скаргу"):
  report_reason = discord.ui.TextInput(
      label="Опишіть порушення або проблему",
      style=discord.TextStyle.paragraph,
      placeholder="Вкажіть нік порушника та суть скарги...",
      required=True,
      max_length=1000,
  )

  async def on_submit(self, interaction: discord.Interaction):
    embed = discord.Embed(
        title="🚨 Нова скарга",
        description=self.report_reason.value,
        color=discord.Color.red(),
    )
    embed.set_author(
        name=interaction.user.name, icon_url=interaction.user.avatar.url
    )

    await interaction.response.send_message(
        "Вашу скаргу успішно надіслано адміністрації!", ephemeral=True
    )


@bot.tree.command(
    name="report", description="Надіслати скаргу на гравця або порушення"
)
async def report(interaction: discord.Interaction):
  await interaction.response.send_modal(ReportModal())


# ==========================================
# 2. КОМАНДИ МОДЕРАЦІЇ (Мут, Бан, Розмут)
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
      f" Користувача {member.mention} успішно забанено. Причина: {reason}",
      ephemeral=True,
  )


@bot.tree.command(name="mute", description="Видати тайм-аут (мут) учаснику")
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
      f" Учаснику {member.mention} видано мут на {minutes} хв. Причина:"
      f" {reason}",
      ephemeral=True,
  )


@bot.tree.command(name="unmute", description="Зняти тайм-аут (мут) з учасника")
@app_commands.default_permissions(moderate_members=True)
async def unmute(interaction: discord.Interaction, member: discord.Member):
  await member.timeout(None)
  await interaction.response.send_message(
      f" Знято мут з користувача {member.mention}.", ephemeral=True
  )


# ==========================================
# 3. ФУНКЦІЯ AI АГЕНТА (Інтеграція чату)
# ==========================================


@bot.tree.command(
    name="ai", description="Поставити запитання AI асистенту в чаті"
)
async def ai_chat(interaction: discord.Interaction, *, prompt: str):
  await interaction.response.defer()  # Дає час на відповідь

  # Тут згодом можна підключити реальний API (OpenAI / Gemini)
  ai_response = (
      f"🤖 **AI Агент:** Я отримав твоє запитання: *'{prompt}'*. (Готовий до"
      " підключення твого API)."
  )

  await interaction.followup.send(ai_response)


# Запуск бота через змінну середовища
TOKEN = os.getenv("DISCORD_TOKEN")
if TOKEN:
  bot.run(TOKEN)
else:
  print("ПОМИЛКА: Не знайдено токен у змінних середовища DISCORD_TOKEN!")
