import os
import asyncio
import discord
from discord.ext import commands
from discord import app_commands
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ==========================================
# 🔑 ТОКЕНИ
# ==========================================
DISCORD_TOKEN = "МТУzMjE0NnU2ODc3NDIyMjAyNw.Gwt2bD.M2oC00uXYWgLb81TSCeUA91P"
TG_TOKEN = "8950607445:AAGIn92dMbqTmOXywvqZg2M_Bq92XVEtftM"

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
# 🛡️ DISCORD: ПОКРАЩЕНА СИСТЕМА ТІКЕТІВ ТА МОДЕРАЦІЯ
# ==========================================

class AdvancedTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🛠️ Технічна підтримка", style=discord.ButtonStyle.primary, custom_id="ticket_tech")
    async def tech_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.create_ticket_channel(interaction, "тех-підтримка", "Опишіть вашу технічну проблему чи баг.")

    @discord.ui.button(label="⚖️ Скарга на порушника", style=discord.ButtonStyle.danger, custom_id="ticket_report")
    async def report_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.create_ticket_channel(interaction, "скарга", "Вкажіть нік порушника та надайте докази (скріншоти/відео).")

    @discord.ui.button(label="❓ Загальне питання", style=discord.ButtonStyle.secondary, custom_id="ticket_other")
    async def other_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.create_ticket_channel(interaction, "питання", "Чим ми можемо вам допомогти?")

    async def create_ticket_channel(self, interaction: discord.Interaction, category_name: str, welcome_text: str):
        guild = interaction.guild
        # Шукаємо або створюємо категорію для тікетів
        category = discord.utils.get(guild.categories, name="🎫 ТІКЕТИ ВАРТА UA")
        if not category:
            category = await guild.create_category("🎫 ТІКЕТИ ВАРТА UA")

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
        }
        
        channel = await guild.create_text_channel(f"ticket-{category_name}-{interaction.user.name}", category=category, overwrites=overwrites)
        
        embed = discord.Embed(
            title=f"🎫 Звернення користувача: {interaction.user.name}",
            description=f"{welcome_text}\n\n🔒 *Цей канал є приватним. Адміністрація скоро зв'яжеться з вами.*",
            color=discord.Color.from_rgb(0, 162, 255)
        )
        embed.set_footer(text="Varta UA • Система безпеки та підтримки")
        
        close_view = CloseTicketView()
        await channel.send(content=f"{interaction.user.mention}, вітаємо!", embed=embed, view=close_view)
        await interaction.response.send_message(f"✅ Ваш тікет успішно створено: {channel.mention}", ephemeral=True)

class CloseTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 Закрити тікет", style=discord.ButtonStyle.danger, custom_id="close_ticket_btn")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🔒 Тікет буде закрито через 5 секунд...", ephemeral=False)
        await asyncio.sleep(5)
        await interaction.channel.delete()

@discord_bot.tree.command(name="setup_tickets", description="Опублікувати нову стильну панель тікетів")
@app_commands.checks.has_permissions(administrator=True)
async def setup_tickets(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🛡️ Центр безпеки та підтримки Varta UA",
        description=(
            "Потрібна допомога, виникла проблема чи хочете повідомити про порушника?\n\n"
            "📌 **Оберіть відповідну категорію за допомогою кнопок нижче:**\n"
            "• **Технічна підтримка** — проблеми з доступом, баги.\n"
            "• **Скарга на порушника** — скарги на гравців або персонал.\n"
            "• **Загальне питання** — будь-які інші запитання."
        ),
        color=discord.Color.from_rgb(0, 120, 255)
    )
    embed.set_footer(text="Varta UA • Project Protection System")
    await interaction.channel.send(embed=embed, view=AdvancedTicketView())
    await interaction.response.send_message("✅ Панель тікетів успішно розгорнуто!", ephemeral=True)

# Команди модерації Discord
@discord_bot.tree.command(name="kick", description="Вигнати порушника з сервера")
@app_commands.checks.has_permissions(kick_members=True)
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "Порушення правил"):
    await member.kick(reason=reason)
    await interaction.response.send_message(f"❌ Користувача {member.mention} вигнано. Причина: {reason}")

@discord_bot.tree.command(name="ban", description="Заблокувати порушника на сервері")
@app_commands.checks.has_permissions(ban_members=True)
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "Порушення правил"):
    await member.ban(reason=reason)
    await interaction.response.send_message(f"⛔ Користувача {member.mention} заблоковано. Причина: {reason}")

@discord_bot.tree.command(name="mute", description="Видати тайм-аут порушнику")
@app_commands.checks.has_permissions(moderate_members=True)
async def mute(interaction: discord.Interaction, member: discord.Member, minutes: int, reason: str = "Порушення порядку"):
    duration = discord.utils.utcnow() + discord.timedelta(minutes=minutes)
    await member.timeout(duration, reason=reason)
    await interaction.response.send_message(f"🔇 Користувача {member.mention} замучено на {minutes} хв. Причина: {reason}")

@discord_bot.tree.command(name="clear", description="Очистити чат від повідомлень")
@app_commands.checks.has_permissions(manage_messages=True)
async def clear(interaction: discord.Interaction, amount: int):
    await interaction.channel.purge(limit=amount)
    await interaction.response.send_message(f"🧹 Очищено {amount} повідомлень.", ephemeral=True)


# ==========================================
# ✈️ TELEGRAM: ПАНЕЛЬ ТА МОДЕРАЦІЯ ЧАТУ
# ==========================================

@dp.message(Command("start"))
async def tg_start(message: types.Message):
    builder = InlineKeyboardBuilder()
    builder.button(text="🌐 Наш Discord", url="https://discord.gg/9qBKQcXCuP")
    builder.button(text="📢 Telegram канал", url="https://t.me/Storm_Bot_Development")
    builder.adjust(1)
    
    await message.answer(
        "🛡️ **Вітаємо у службі підтримки Варта UA!**\n\n"
        "Цей бот забезпечує модерацію чату та зв'язок із проєктом.",
        reply_markup=builder.as_markup()
    )

@dp.message(Command("ban"))
async def tg_ban(message: types.Message):
    if not message.reply_to_message:
        return await message.reply("⚠️ Відповіжте цією командою на повідомлення порушника!")
    try:
        member = await message.chat.get_member(message.from_user.id)
        if member.status in ["administrator", "creator"]:
            target_user = message.reply_to_message.from_user
            await message.chat.ban(user_id=target_user.id)
            await message.reply(f"⛔ Користувача {target_user.full_name} забанено в чаті!")
    except Exception as e:
        await message.reply(f"❌ Помилка модерації: перевірте права бота в чаті.")

@dp.message(Command("mute"))
async def tg_mute(message: types.Message):
    if not message.reply_to_message:
        return await message.reply("⚠️ Відповіжте цією командою на повідомлення порушника!")
    try:
        member = await message.chat.get_member(message.from_user.id)
        if member.status in ["administrator", "creator"]:
            target_user = message.reply_to_message.from_user
            permissions = types.ChatPermissions(can_send_messages=False)
            await message.chat.restrict(user_id=target_user.id, permissions=permissions)
            await message.reply(f"🔇 Користувача {target_user.full_name} замучено!")
    except Exception as e:
        await message.reply(f"❌ Помилка модерації: перевірте права бота в чаті.")

@dp.message(Command("unmute"))
async def tg_unmute(message: types.Message):
    if not message.reply_to_message:
        return await message.reply("⚠️ Відповіжте цією командою на повідомлення користувача!")
    try:
        member = await message.chat.get_member(message.from_user.id)
        if member.status in ["administrator", "creator"]:
            target_user = message.reply_to_message.from_user
            permissions = types.ChatPermissions(
                can_send_messages=True, can_send_media_messages=True, 
                can_send_other_messages=True, can_add_web_page_previews=True
            )
            await message.chat.restrict(user_id=target_user.id, permissions=permissions)
            await message.reply(f"🔊 З користувача {target_user.full_name} знято мут!")
    except Exception as e:
        await message.reply(f"❌ Помилка.")


# ==========================================
# 🚀 ЗАПУСК БОТІВ
# ==========================================
@discord_bot.event
async def on_ready():
    await discord_bot.tree.sync()
    discord_bot.add_view(AdvancedTicketView())
    discord_bot.add_view(CloseTicketView())
    print(f"✅ Discord бот успішно запущено: {discord_bot.user}")

async def main():
    asyncio.create_task(dp.start_polling(tg_bot))
    print("✅ Telegram бот запущено в режимі polling.")
    await discord_bot.start(DISCORD_TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
