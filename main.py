import os
import discord
from discord import app_commands
from discord.ext import commands
from google import genai

# Ініціалізація бота
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Підключення до Gemini API через нову бібліотеку
gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


@bot.event
async def on_ready():
  print(f"Бот {bot.user} успішно запущений і підключений до Gemini AI!")
  try:
    synced = await bot.tree.sync()
    print(f"Синхронізовано слеш-команд: {len(synced)}")
  except Exception as e:
    print(e)


# ==========================================
# КОМАНДА AI АГЕНТА (GEMINI)
# ==========================================


@bot.tree.command(
    name="ai", description="Поставити запитання штучному інтелекту Gemini"
)
async def ai_chat(interaction: discord.Interaction, *, prompt: str):
  await interaction.response.defer()

  try:
    # Використовуємо актуальну модель gemini-3.8-flash за рекомендацією API
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
        f"❌ Виникла помилка при зверненні до Gemini AI: `{e}`"
    )


# Запуск бота
TOKEN = os.getenv("DISCORD_TOKEN")
if TOKEN:
  bot.run(TOKEN)
else:
  print("ПОМИЛКА: Не знайдено токен Discord!")
