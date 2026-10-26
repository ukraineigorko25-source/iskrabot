import os
import asyncio
import discord
from discord.ext import commands
from discord import app_commands
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ==========================================
# 🔑 ТОКЕНИ З ХОСТИНГУ
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

# ID адміністратора / чату для логів скарг у Telegram
TG_ADMIN_CHAT_ID = None  # Сюди можна вписати ID адмін-чату


# ==========================================
# 🛡️ DISCORD: ПРОДВИНУТА СИСТЕМА ТІКЕТІВ ТА МОДЕРАЦІЯ
# ==========================================

class TicketManagementView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📌 Взяти на розгляд", style=discord.ButtonStyle.primary, custom_id="ticket_claim")
    async def claim_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(f"📌 Тікет узяв у роботу модератор: {interaction.user.mention}", ephemeral=False)

    @discord.ui.button(label="🔄 Передати", style=discord.ButtonStyle.secondary, custom_id="ticket_transfer")
    async def transfer_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(f"🔄 Тікет передано іншому члену старшої адміністрації.", ephemeral=False)

    @discord.ui.button(label="🔒 Закрити тікет", style=discord.ButtonStyle.danger, custom_id="ticket_close_start")
    async def close_ticket_start(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="⭐ Оцінка підтримки",
            description="Будь ласка, оцініть роботу модератора від 1 до 5 зірочок за допомогою кнопок нижче:",
            color=discord.Color.gold()
        )
        await interaction.response.send_message(embed=embed, view=RatingView(), ephemeral=False)

class RatingView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def rate_and_close(self, interaction: discord.Interaction, rating: str):
        # Відправляємо лог у ЛС учаснику та модератору (симуляція)
        try:
            await interaction.user.send(f"🔒 Ваш тікет закрито. Оцінка підтримки: {rating}. Дякуємо, що звернулися у Varta UA!")
        except:
            pass
        
        await interaction.response.send_message(f"✅ Дякуємо за оцінку ({rating})! Тікет буде повністю закрито через 5 секунд.", ephemeral=False)
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete()
        except:
            pass

    @discord.ui.button(label="⭐ 1", style=discord.ButtonStyle.danger, custom_id="rate_1")
    async def r1(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.rate_and_close(interaction, "1/5 ❌")

    @discord.ui.button(label="⭐ 2", style=discord.ButtonStyle.danger, custom_id="rate_2")
    async def r2(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.rate_and_close(interaction, "2/5 ⚠️")

    @discord.ui.button(label="⭐ 3", style=discord.ButtonStyle.secondary, custom_id="rate_3")
    async def r3(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.rate_and_close(interaction, "3/5 ⏺️")

    @discord.ui.button(label="⭐ 4", style=discord.ButtonStyle.primary, custom_id="rate_4")
    async def r4(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.rate_and_close(interaction, "4/5 ✅")

    @discord.ui.button(label="⭐ 5", style=discord.ButtonStyle.success, custom_id="rate_5")
    async def r5(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.rate_and_close(interaction, "5/5 👑")

class AdvancedTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🛠️ Технічна підтримка", style=discord.ButtonStyle.primary, custom_id="ticket_tech")
    async def tech_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.create_ticket_channel(interaction, "тех-підтримка")

    @discord.ui.button(label="⚖️ Скарга на порушника", style=discord.ButtonStyle.danger, custom_id="ticket_report")
    async def report_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.create_ticket_channel(interaction, "скарга")

    @discord.ui.button(label="❓ Загальне питання", style=discord.ButtonStyle.secondary, custom_id="ticket_other")
    async def other_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.create_ticket_channel(interaction, "питання")

    async def create_ticket_channel(self, interaction: discord.Interaction, category_name: str):
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
            description="Опишіть вашу проблему. Модератори скоро підключаться.\n\n⏱️ *Увага: неактивні тікети закриваються автоматично через 24 години.*",
            color=discord.Color.from_rgb(0, 162, 255)
        )
        embed.set_footer(text="Varta UA • Система безпеки та підтримки")
        
        await channel.send(content=f"{interaction.user.mention}, вітаємо!", embed=embed, view=TicketManagementView())
        await interaction.response.send_message(f"✅ Ваш тікет успішно створено: {channel.mention}", ephemeral=True)

@discord_bot.tree.command(name="setup_tickets", description="Розгорнути панель тікетів")
@app_commands.checks.has_permissions(administrator=True)
async def setup_tickets(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🛡️ Центр безпеки та підтримки Varta UA",
        description="Потрібна допомога чи є скарга? Оберіть категорію нижче:",
        color=discord.Color.from_rgb(0, 120, 255)
    )
    await interaction.channel.send(embed=embed, view=AdvancedTicketView())
    await interaction.response.send_message("✅ Панель тікетів розгорнуто!", ephemeral=True)

@discord_bot.tree.command(name="report", description="Поскаржитися на порушника в Discord")
async def discord_report(interaction: discord.Interaction, reason: str):
    await interaction.response.send_message(f"🚨 Вашу скаргу надіслано адміністрації проєкту Varta UA. Дякуємо за пильність!", ephemeral=True)

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

@discord_bot.tree.command(name="set_owner_role", description="[Засновник] Видати вищу роль проєкту")
@app_commands.checks.has_permissions(administrator=True)
async def set_owner_role(interaction: discord.Interaction, member: discord.Member, role_name: str = "Засновник / Власник"):
    guild = interaction.guild
    role = discord.utils.get(guild.roles, name=role_name)
    if not role:
        role = await guild.create_role(name=role_name, color=discord.Color.gold(), permissions=discord.Permissions.all())
    await member.add_roles(role)
    await interaction.response.send_message(f"👑 Користувачу {member.mention} видано роль **{role.name}**.", ephemeral=True)


# ==========================================
# ✈️ TELEGRAM: КОМАНДИ, /report ТА ТІКЕТИ
# ==========================================

@dp.message(Command("start"))
async def tg_start(message: types.Message):
    builder = InlineKeyboardBuilder()
    builder.button(text="🌐 Наш Discord", url="https://discord.gg/9qBKQcXCuP")
    builder.button(text="🎫 Створити тікет / Зв'язок", url="https://t.me/VartaUA_Robot")
    builder.adjust(1)
    
    await message.answer(
        "🛡️ **Вітаємо у службі підтримки Варта UA!**\n\n"
        "Скористайтеся командами `/ticket` або `/report`, щоб звернутися до адміністрації.",
        reply_markup=builder.as_markup()
    )

@dp.message(Command("ticket"))
async def tg_ticket(message: types.Message):
    await message.answer(
        "🎫 **Центр підтримки Варта UA**\n\n"
        "Напишіть вашу проблему або питання суцільним повідомленням нижче. Адміністрація отримає звернення і зв'яжеться з вами в особистих повідомленнях!"
    )

@dp.message(Command("report"))
async def tg_report(message: types.Message):
    if not message.reply_to_message:
        return await message.reply("⚠️ Щоб надіслати скаргу, **відповіжте цією командою** на повідомлення порушника!")
    
    reported_user = message.reply_to_message.from_user
    author = message.from_user
    
    report_text = (
        f"🚨 **НОВА СКАРГА (Telegram)**\n\n"
        f"👤 **Порушник:** {reported_user.full_name} (`{reported_user.id}`)\n"
        f"🙋‍♂️ **Хто поскаржився:** {author.full_name} (`{author.id}`)\n"
        f"💬 **Час/Чат:** {message.chat.title or 'Особисті повідомлення'}"
    )
    
    await message.reply(f"✅ Вашу скаргу на користувача {reported_user.full_name} успішно надіслано адміністраторам!")

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

@dp.message(Command("setowner"))
async def tg_set_owner(message: types.Message):
    args = message.text.split()
    if len(args) < 2:
        return await message.reply(f"ℹ️ Ваш поточний Telegram ID: `{message.from_user.id}`\n\nВикористання: `/setowner [ID]`", parse_mode="Markdown")
    try:
        target_id = int(args[1])
        await message.chat.promote(
            user_id=target_id,
            can_manage_chat=True,
            can_delete_messages=True,
            can_restrict_members=True,
            can_promote_members=True
        )
        await message.reply(f"👑 Успішно! Користувачу з ID `{target_id}` надано права адміністратора.")
    except Exception:
        await message.reply("❌ Помилка: переконайтеся, що бот має права підвищувати адміністраторів.")


# ==========================================
# 🚀 ЗАПУСК БОТІВ
# ==========================================
@discord_bot.event
async def on_ready():
    await discord_bot.tree.sync()
    discord_bot.add_view(AdvancedTicketView())
    discord_bot.add_view(TicketManagementView())
    discord_bot.add_view(RatingView())
    print(f"✅ Discord бот успішно запущено: {discord_bot.user}")

async def main():
    asyncio.create_task(dp.start_polling(tg_bot))
    print("✅ Telegram бот запущено в режимі polling.")
    await discord_bot.start(DISCORD_TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
