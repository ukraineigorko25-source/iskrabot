import os
import asyncio
import discord
from discord.ext import commands
from discord import app_commands
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

# ==========================================
# 🔑 ЗЧИТУВАННЯ ТОКЕНІВ (БЕЗПЕЧНО ЧЕРЕЗ ХОСТИНГ)
# ==========================================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
TG_TOKEN = os.getenv("TG_TOKEN")

# ==========================================
# 🤖 ІНІЦІАЛІЗАЦІЯ БОТІВ
# ==========================================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
discord_bot = commands.Bot(command_prefix="!", intents=intents)

tg_bot = Bot(token=TG_TOKEN)
dp = Dispatcher()

# ==========================================
# 🛡️ DISCORD: МОДЕРАЦІЯ ТА СИСТЕМА УПРАВЛІННЯ
# ==========================================

@discord_bot.tree.command(name="kick", description="Вигнати користувача з сервера")
@app_commands.checks.has_permissions(kick_members=True)
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "Порушення правил"):
    await member.kick(reason=reason)
    await interaction.response.send_message(f"❌ Користувача {member.mention} вигнано! Причина: {reason}")

@discord_bot.tree.command(name="ban", description="Заблокувати користувача")
@app_commands.checks.has_permissions(ban_members=True)
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "Порушення правил"):
    await member.ban(reason=reason)
    await interaction.response.send_message(f"⛔ Користувача {member.mention} забанено! Причина: {reason}")

@discord_bot.tree.command(name="mute", description="Замутити користувача (видати тайм-аут)")
@app_commands.checks.has_permissions(moderate_members=True)
async def mute(interaction: discord.Interaction, member: discord.Member, minutes: int, reason: str = "Порушення порядку"):
    duration = discord.utils.utcnow() + discord.timedelta(minutes=minutes)
    await member.timeout(duration, reason=reason)
    await interaction.response.send_message(f"🔇 Користувача {member.mention} замучено на {minutes} хвилин. Причина: {reason}")

@discord_bot.tree.command(name="clear", description="Очистити чат")
@app_commands.checks.has_permissions(manage_messages=True)
async def clear(interaction: discord.Interaction, amount: int):
    await interaction.channel.purge(limit=amount)
    await interaction.response.send_message(f"🧹 Видалено {amount} повідомлень.", ephemeral=True)

@discord_bot.tree.command(name="say", description="Написати оголошення від імені бота VARTA UA")
@app_commands.checks.has_permissions(administrator=True)
async def say(interaction: discord.Interaction, message: str):
    await interaction.channel.send(message)
    await interaction.response.send_message("Надіслано!", ephemeral=True)

class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📩 Відкрити тікет", style=discord.ButtonStyle.primary, custom_id="open_ticket")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        channel = await guild.create_text_channel(f"тікет-{interaction.user.name}", overwrites=overwrites)
        await channel.send(f"Вітаємо {interaction.user.mention}! Опишіть вашу проблему тут. Адміністрація скоро відповість.")
        await interaction.response.send_message(f"Тікет створено: {channel.mention}", ephemeral=True)

    @discord.ui.button(label="⚠️ Скарга на команду", style=discord.ButtonStyle.danger, custom_id="open_report")
    async def open_report(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        channel = await guild.create_text_channel(f"скарга-{interaction.user.name}", overwrites=overwrites)
        await channel.send(f"⚠️ {interaction.user.mention}, напишіть деталі скарги на члена команди VARTA UA. Розглядає виключно керівництво!")
        await interaction.response.send_message(f"Канал для скарги створено: {channel.mention}", ephemeral=True)

@discord_bot.tree.command(name="setup_tickets", description="Опублікувати меню підтримки та скарг")
@app_commands.checks.has_permissions(administrator=True)
async def setup_tickets(interaction: discord.Interaction):
    embed = discord.Embed(
        title="💬 Центр підтримки VARTA UA",
        description="Оберіть необхідну опцію нижче для створення приватного звернення:",
        color=discord.Color.blue()
    )
    await interaction.channel.send(embed=embed, view=TicketView())
    await interaction.response.send_message("Меню звернень створено!", ephemeral=True)


# ==========================================
# ✈️ TELEGRAM: ПОЛІЦЕЙСЬКІ ТА МОДЕРАЦІЙНІ КОМАНДИ
# ==========================================

@dp.message(Command("ban"))
async def tg_ban(message: types.Message):
    if not message.reply_to_message:
        return await message.reply("⚠️ Відповіжте цією командою на повідомлення порушника!")
    
    member = await message.chat.get_member(message.from_user.id)
    if member.status in ["administrator", "creator"]:
        await message.chat.ban(user_id=message.reply_to_message.from_user.id)
        await message.reply(f"⛔ Користувача {message.reply_to_message.from_user.full_name} забанено в чаті!")

@dp.message(Command("mute"))
async def tg_mute(message: types.Message):
    if not message.reply_to_message:
        return await message.reply("⚠️ Відповіжте цією командою на повідомлення порушника!")
        
    member = await message.chat.get_member(message.from_user.id)
    if member.status in ["administrator", "creator"]:
        permissions = types.ChatPermissions(can_send_messages=False)
        await message.chat.restrict(user_id=message.reply_to_message.from_user.id, permissions=permissions)
        await message.reply(f"🔇 Користувача {message.reply_to_message.from_user.full_name} замучено!")

@dp.message(Command("unmute"))
async def tg_unmute(message: types.Message):
    if not message.reply_to_message:
        return await message.reply("⚠️ Відповіжте цією командою на повідомлення користувача!")
        
    member = await message.chat.get_member(message.from_user.id)
    if member.status in ["administrator", "creator"]:
        permissions = types.ChatPermissions(can_send_messages=True, can_send_media_messages=True, can_send_other_messages=True)
        await message.chat.restrict(user_id=message.reply_to_message.from_user.id, permissions=permissions)
        await message.reply(f"🔊 З користувача {message.reply_to_message.from_user.full_name} знято мут!")

@dp.message(Command("say"))
async def tg_say(message: types.Message):
    member = await message.chat.get_member(message.from_user.id)
    if member.status in ["administrator", "creator"]:
        text = message.text.replace("/say", "").strip()
        if text:
            await message.delete()
            await message.answer(text)


# ==========================================
# 🚀 ЗАПУСК ОБОХ БОТІВ ПАРАЛЕЛЬНО
# ==========================================
@discord_bot.event
async def on_ready():
    await discord_bot.tree.sync()
    discord_bot.add_view(TicketView())
    print(f"✅ Discord бот успішно запущено: {discord_bot.user}")

async def main():
    asyncio.create_task(dp.start_polling(tg_bot))
    print("✅ Telegram бот запущено в режимі polling.")
    await discord_bot.start(DISCORD_TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
