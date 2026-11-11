import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "-1002270157899"))
CHANNEL_INVITE_LINK = os.getenv(
    "CHANNEL_INVITE_LINK", "https://t.me/+NHLJcjDgBIszZTky"
).strip()
GROUP_ID = int(os.getenv("GROUP_ID", "-1003985789251"))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not configured")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

router = Router()
# Последнее сообщение-приглашение для пользователя, чтобы не засорять группу.
last_prompts: dict[tuple[int, int], int] = {}


def subscription_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Подписаться на канал", url=CHANNEL_INVITE_LINK)],
            [InlineKeyboardButton(text="Проверить подписку", callback_data="check_subscription")],
        ]
    )


async def is_subscribed(bot: Bot, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
    except (TelegramBadRequest, TelegramForbiddenError) as exc:
        logger.warning("Cannot check channel membership for %s: %s", user_id, exc)
        return False

    if member.status in {ChatMemberStatus.CREATOR, ChatMemberStatus.ADMINISTRATOR,
                         ChatMemberStatus.MEMBER}:
        return True
    # Restricted users are subscribers while their membership is still active.
    return member.status == ChatMemberStatus.RESTRICTED and bool(member.is_member)


async def remove_old_prompt(bot: Bot, chat_id: int, user_id: int) -> None:
    key = (chat_id, user_id)
    message_id = last_prompts.pop(key, None)
    if message_id is None:
        return
    try:
        await bot.delete_message(chat_id, message_id)
    except TelegramBadRequest:
        pass


async def send_subscription_prompt(message: Message, bot: Bot) -> None:
    if not message.from_user:
        return
    await remove_old_prompt(bot, message.chat.id, message.from_user.id)
    prompt = await message.answer(
        "Чтобы писать в этом чате, сначала подпишитесь на канал.",
        reply_markup=subscription_keyboard(),
    )
    last_prompts[(message.chat.id, message.from_user.id)] = prompt.message_id


@router.message(F.chat.id == GROUP_ID)
async def gate_group_messages(message: Message, bot: Bot) -> None:
    if not message.from_user or message.from_user.is_bot:
        return

    if await is_subscribed(bot, message.from_user.id):
        await remove_old_prompt(bot, message.chat.id, message.from_user.id)
        return

    try:
        await message.delete()
    except (TelegramBadRequest, TelegramForbiddenError) as exc:
        logger.warning("Cannot delete message %s in %s: %s", message.message_id, message.chat.id, exc)
    await send_subscription_prompt(message, bot)


@router.callback_query(F.data == "check_subscription")
async def check_subscription(callback: CallbackQuery, bot: Bot) -> None:
    if not callback.from_user or not callback.message:
        return
    if await is_subscribed(bot, callback.from_user.id):
        await callback.answer("Подписка найдена. Теперь можно общаться в чате.", show_alert=True)
        await remove_old_prompt(bot, callback.message.chat.id, callback.from_user.id)
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass
    else:
        await callback.answer("Подписка пока не найдена. Подпишитесь и попробуйте снова.", show_alert=True)


@router.message(CommandStart())
async def start_private(message: Message) -> None:
    await message.answer("Добавьте меня администратором в нужную группу и канал.")


async def main() -> None:
    bot = Bot(BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    logger.info("Bot started; group=%s channel=%s", GROUP_ID, CHANNEL_ID)
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
