import os
import asyncio
import discord
from discord.ext import commands
from discord import app_commands
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ==========================================
# 🔑 ТОКЕНИ З БЕЗПЕЧНОГО СЕРЕДОВИЩА ХОСТИНГУ
# ==========================================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
TG_TOKEN = os.getenv("TG_TOKEN")

if not DISCORD_TOKEN:
    print("❌ Помилка: Не знайдено DISCORD_TOKEN!")
if not TG_TOKEN:
    print("❌ Помилка: Не знайдено TG_TOKEN!")

# ==========================================
# 🤖 ІНІЦІАЛІЗАЦІЯ БОТІВ
# ==========================================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
discord_bot = commands.Bot(command_prefix="!", intents=intents)

tg_bot = Bot(token=TG_TOKEN)
dp = Dispatcher()

# ID Засновника (можеш сюди вписати свій Telegram ID або Discord ID для додаткової перевірки, якщо потрібно)
OWNER_TG_ID = 0  # Сюди можна вписати твій чи другий головний ID за бажанням


# ==========================================
# 🛡️ DISCORD: ТІКЕТИ, МОДЕРАЦІЯ ТА ПРАВА ЗААСНОВНИКА
# ==========================================

class AdvancedTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🛠️ Технічна підтримка", style=discord.ButtonStyle.primary, custom_id="ticket_tech")
    async def tech_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.create_ticket_channel(interaction, "тех-підтримка", "Опишіть вашу технічну проблему чи баг.")

    @discord.ui.button(label="⚖️ Скарга на порушника", style=discord.ButtonStyle.danger, custom_id="ticket_report")
    async def report_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.create_ticket_channel(interaction, "скарга", "Вкажіть нік порушника та надайте докази.")

    @discord.ui.button(label="❓ Загальне питання", style=discord.ButtonStyle.secondary, custom_id="ticket_other")
    async def other_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.create_ticket_channel(interaction, "питання", "Чим ми можемо вам допомогти?")

    async def create_ticket_channel(self, interaction: discord.Interaction, category_name: str, welcome_text: str):
        guild = interaction.guild
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
            description=f"{welcome_text}\n\n🔒 *Цей канал є приватним.*",
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

@discord_bot.tree.command(name="setup_tickets", description="Опублікувати панель тікетів")
@app_commands.checks.has_permissions(administrator=True)
async def setup_tickets(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🛡️ Центр безпеки та підтримки Varta UA",
        description="Потрібна допомога чи хочете повідомити про порушника?\n\n📌 **Оберіть категорію нижче:**",
        color=discord.Color.from_rgb(0, 120, 255)
    )
    embed.set_footer(text="Varta UA • Project Protection System")
    await interaction.channel.send(embed=embed, view=AdvancedTicketView())
    await interaction.response.send_message("✅ Панель тікетів успішно розгорнуто!", ephemeral=True)

@discord_bot.tree.command(name="kick", description="Вигнати порушника")
@app_commands.checks.has_permissions(kick_members=True)
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "Порушення правил"):
    await member.kick(reason=reason)
    await interaction.response.send_message(f"❌ Користувача {member.mention} вигнано. Причина: {reason}")

@discord_bot.tree.command(name="ban", description="Заблокувати порушника")
@app_commands.checks.has_permissions(ban_members=True)
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "Порушення правил"):
    await member.ban(reason=reason)
    await interaction.response.send_message(f"⛔ Користувача {member.mention} заблоковано. Причина: {reason}")

@discord_bot.tree.command(name="mute", description="Видати тайм-аут")
@app_commands.checks.has_permissions(moderate_members=True)
async def mute(interaction: discord.Interaction, member: discord.Member, minutes: int, reason: str = "Порушення порядку"):
    duration = discord.utils.utcnow() + discord.timedelta(minutes=minutes)
    await member.timeout(duration, reason=reason)
    await interaction.response.send_message(f"🔇 Користувача {member.mention} замучено на {minutes} хв.")

@discord_bot.tree.command(name="clear", description="Очистити чат")
@app_commands.checks.has_permissions(manage_messages=True)
async def clear(interaction: discord.Interaction, amount: int):
    await interaction.channel.purge(limit=amount)
    await interaction.response.send_message(f"🧹 Очищено {amount} повідомлень.", ephemeral=True)

# Спеціальна команда засновника в Discord для видачі ролі/прав через бота
@discord_bot.tree.command(name="set_owner_role", description="[Тільки засновник] Видати вищу роль проєкту через бота")
@app_commands.checks.has_permissions(administrator=True)
async def set_owner_role(interaction: discord.Interaction, member: discord.Member, role_name: str = "Засновник / Власник"):
    guild = interaction.guild
    # Шукаємо або створюємо найвищу роль
    role = discord.utils.get(guild.roles, name=role_name)
    if not role:
        role = await guild.create_role(name=role_name, color=discord.Color.gold(), permissions=discord.Permissions.all())
    
    try:
        await member.add_roles(role)
        await interaction.response.send_message(f"👑 Успішно! Користувачу {member.mention} видано вищу роль **{role.name}** від імені бота.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Помилка видачі ролі: перевірте ієрархію ролей бота.", ephemeral=True)


# ==========================================
# ✈️ TELEGRAM: МОДЕРАЦІЯ, ТІКЕТИ ТА ПРАВА ЗААСНОВНИКА
# ==========================================

@dp.message(Command("start"))
async def tg_start(message: types.Message):
    builder = InlineKeyboardBuilder()
    builder.button(text="🌐 Наш Discord", url="https://discord.gg/9qBKQcXCuP")
    builder.button(text="🎫 Створити тікет / Зв'язок", url="https://t.me/VartaUA_Robot")
    builder.adjust(1)
    
    await message.answer(
        "🛡️ **Вітаємо у службі підтримки Варта UA!**\n\n"
        "Скористайтеся кнопками нижче для зв'язку або переходу на ресурси.",
        reply_markup=builder.as_markup()
    )

@dp.message(Command("ticket"))
async def tg_ticket(message: types.Message):
    await message.answer(
        "🎫 **Центр підтримки Варта UA**\n\n"
        "Опишіть вашу проблему або скаргу сюди в повідомленнях, і адміністрація обов'язково вам відповість!"
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
            await message.reply(f"⛔ Користувача {target_user.full_name} забанено!")
    except Exception:
        await message.reply("❌ Помилка: перевірте права адміністратора у бота.")

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
    except Exception:
        await message.reply("❌ Помилка: перевірте права адміністратора у бота.")

# Команда для Telegram, щоб дати права адміністратора / статус власнику за Telegram ID
@dp.message(Command("setowner"))
async def tg_set_owner(message: types.Message):
    # Використовується так: /setowner [ID_користувача]
    args = message.text.split()
    if len(args) < 2:
        return await message.reply(f"ℹ️ Ваш поточний Telegram ID: `{message.from_user.id}`\n\nВикористання: `/setowner [ID]` для надання прав засновника через бота.", parse_mode="Markdown")
    
    try:
        target_id = int(args[1])
        # Надаємо повні права адміністратора в чаті через бота (якщо бот має право підвищувати адмінів)
        await message.chat.promote(
            user_id=target_id,
            is_anonymous=False,
            can_manage_chat=True,
            can_delete_messages=True,
            can_manage_video_chats=True,
            can_restrict_members=True,
            can_promote_members=True,
            can_change_info=True,
            can_invite_users=True,
            can_post_messages=True,
            can_edit_messages=True,
            can_pin_messages=True
        )
        await message.reply(f"👑 Успішно! Користувачу з ID `{target_id}` надано повні права адміністратора/засновника в цьому чаті.")
    except Exception as e:
        await message.reply(f"❌ Помилка: переконайтеся, що бот є адміністратором з правом додавати інших адміністраторів.")


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
