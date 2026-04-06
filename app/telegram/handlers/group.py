"""Хендлеры группового чата."""

from __future__ import annotations

import asyncio
import logging
import re

from aiogram import Bot, F, Router
from aiogram.filters import CommandStart
from aiogram.types import ChatPermissions, Message, MessageEntity

from app.core.config import settings
from app.core.telegram_config import PENDING_REPLY_DELAY_SECONDS
from app.models.group_action import GroupMessageAction
from app.models.incoming_message import IncomingMessage
from app.telegram.services.group_service import GroupService
from app.utils.logging import compact_log_text

router = Router(name="group")
group_service = GroupService()
logger = logging.getLogger(__name__)
_background_tasks: set[asyncio.Task] = set()

_QUESTION_PATTERN = re.compile(
    r"(^|\s)(где|как|когда|сколько|можно|почему|зачем|что|кто|куда|какой|какая|какие)\b",
    re.IGNORECASE,
)
_LINK_PATTERN = re.compile(r"https?://|t\.me/|www\.", re.IGNORECASE)


@router.message(CommandStart())
async def start(message: Message) -> None:
    """Обрабатывает `/start`."""
    logger.info(
        "Command /start received: chat_id=%s user_id=%s message_id=%s",
        message.chat.id,
        message.from_user.id if message.from_user else None,
        message.message_id,
    )
    await message.answer("Бот запущен.")
    logger.info(
        "Command /start answered: chat_id=%s message_id=%s",
        message.chat.id,
        message.message_id,
    )


@router.message(F.text)
async def group_message(message: Message) -> None:
    """Обрабатывает текстовые сообщения группы."""
    incoming_message = _normalize_message(message)
    if incoming_message is None:
        logger.info(
            "Group message skipped during normalization: chat_id=%s message_id=%s "
            "chat_type=%s has_text=%s",
            message.chat.id,
            message.message_id,
            message.chat.type,
            bool(message.text and message.text.strip()),
        )
        return

    logger.info(
        "Group message normalized: chat_id=%s user_id=%s message_id=%s "
        "reply_to_bot=%s mentions_bot=%s has_question=%s has_links=%s "
        "mention_count=%s mention_targets=%s forward_chat_id=%s lang=%s text='%s'",
        incoming_message.chat_id,
        incoming_message.user_id,
        incoming_message.message_id,
        incoming_message.is_reply_to_bot,
        incoming_message.mentions_bot,
        incoming_message.has_question,
        incoming_message.has_links,
        incoming_message.mention_count,
        incoming_message.mention_targets,
        incoming_message.forward_chat_id,
        incoming_message.user_language,
        compact_log_text(incoming_message.text, 500),
    )

    result = await group_service.process_message(incoming_message)
    if result.action == GroupMessageAction.DELETE_SPAM:
        try:
            await message.delete()
        except Exception:
            logger.warning(
                "Failed to delete spam message: chat_id=%s user_id=%s message_id=%s",
                message.chat.id,
                message.from_user.id,
                message.message_id,
            )
        try:
            await message.bot.ban_chat_member(
                chat_id=message.chat.id,
                user_id=message.from_user.id,
            )
            logger.info(
                "Group message deleted and user banned: chat_id=%s user_id=%s message_id=%s",
                message.chat.id,
                message.from_user.id,
                message.message_id,
            )
        except Exception:
            logger.warning(
                "Failed to ban user: chat_id=%s user_id=%s message_id=%s",
                message.chat.id,
                message.from_user.id,
                message.message_id,
            )
        return

    if result.action == GroupMessageAction.MUTE_USER:
        try:
            await message.bot.restrict_chat_member(
                chat_id=message.chat.id,
                user_id=message.from_user.id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=result.mute_until,
            )
            logger.info(
                "Group user muted: chat_id=%s user_id=%s message_id=%s until_date=%s",
                message.chat.id,
                message.from_user.id,
                message.message_id,
                result.mute_until.isoformat() if result.mute_until else None,
            )
        except Exception:
            logger.warning(
                "Failed to mute user: chat_id=%s user_id=%s message_id=%s",
                message.chat.id,
                message.from_user.id,
                message.message_id,
            )

    if result.action == GroupMessageAction.PENDING_REPLY:
        task = asyncio.create_task(
            _delayed_answer_check(
                bot=message.bot,
                chat_id=message.chat.id,
            )
        )
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
        logger.info(
            "Group message scheduled for delayed reply: chat_id=%s user_id=%s message_id=%s",
            message.chat.id,
            message.from_user.id,
            message.message_id,
        )
        return

    if result.reply_text:
        await message.reply(result.reply_text)
        logger.info(
            "Group message replied: chat_id=%s user_id=%s message_id=%s answer='%s'",
            message.chat.id,
            message.from_user.id,
            message.message_id,
            compact_log_text(result.reply_text, 700),
        )
        return

    logger.info(
        "Group message ignored without reply: chat_id=%s user_id=%s message_id=%s",
        message.chat.id,
        message.from_user.id,
        message.message_id,
    )


def _normalize_message(message: Message) -> IncomingMessage | None:
    """Превращает aiogram Message в IncomingMessage."""
    if message.chat.type not in {"group", "supergroup"}:
        return None
    if message.from_user is None or not message.text:
        return None

    text = message.text.strip()
    if not text:
        return None

    entities = list(message.entities or [])
    bot_username = (settings.bot_username or "").casefold()
    return IncomingMessage.build(
        chat_id=message.chat.id,
        user_id=message.from_user.id,
        message_id=message.message_id,
        text=text,
        is_reply_to_bot=_is_reply_to_bot(message),
        mentions_bot=_mentions_bot(text, entities, bot_username),
        has_question=_is_question(text),
        has_links=bool(_LINK_PATTERN.search(text))
        or any(entity.type in {"url", "text_link"} for entity in entities),
        mention_count=max(
            text.count("@"),
            sum(1 for entity in entities if entity.type in {"mention", "text_mention"}),
        ),
        forward_chat_id=_get_forward_chat_id(message),
        reply_to_user_id=_get_reply_to_user_id(message),
        mention_targets=_extract_mention_targets(text, entities, bot_username),
        user_language=message.from_user.language_code or "ru",
    )


def _extract_mention_targets(
    text: str,
    entities: list[MessageEntity],
    bot_username: str,
) -> tuple[str, ...]:
    """Возвращает список username'ов упомянутых людей, кроме бота."""
    targets: list[str] = []
    for entity in entities:
        if entity.type == "mention":
            username = text[entity.offset : entity.offset + entity.length].lstrip("@").casefold()
            if username and username != bot_username:
                targets.append(username)
        elif entity.type == "text_mention" and entity.user is not None:
            username = (entity.user.username or "").casefold()
            if username and username != bot_username:
                targets.append(username)
    return tuple(targets)


def _is_question(text: str) -> bool:
    """Проверяет, является ли сообщение вопросом."""
    return text.endswith("?") or bool(_QUESTION_PATTERN.search(text))


def _mentions_bot(
    text: str,
    entities: list[MessageEntity],
    bot_username: str,
) -> bool:
    """Проверяет явное упоминание бота."""
    if not bot_username:
        return False
    expected = f"@{bot_username}"
    if expected in text.casefold():
        return True
    return any(
        entity.type == "mention"
        and text[entity.offset : entity.offset + entity.length].casefold() == expected
        for entity in entities
    )


def _is_reply_to_bot(message: Message) -> bool:
    """Проверяет, что сообщение является reply на бота."""
    if message.reply_to_message is None or message.reply_to_message.from_user is None:
        return False
    if settings.bot_username:
        return (
            message.reply_to_message.from_user.username or ""
        ).casefold() == settings.bot_username.casefold()
    return bool(message.reply_to_message.from_user.is_bot)


def _get_forward_chat_id(message: Message) -> int | None:
    """Извлекает source chat id из forward metadata."""
    origin = getattr(message, "forward_origin", None)
    chat = getattr(origin, "chat", None)
    if chat is not None:
        return chat.id
    forward_from_chat = getattr(message, "forward_from_chat", None)
    if forward_from_chat is not None:
        return forward_from_chat.id
    return None


def _get_reply_to_user_id(message: Message) -> int | None:
    """Извлекает user_id автора сообщения, на которое пришёл reply."""
    if message.reply_to_message is None or message.reply_to_message.from_user is None:
        return None
    return message.reply_to_message.from_user.id


async def _delayed_answer_check(bot: Bot, chat_id: int) -> None:
    """Ждёт PENDING_REPLY_DELAY_SECONDS, затем отправляет ответы на ожидающие вопросы.

    Запускается как asyncio.create_task — не блокирует основной handler.
    """
    await asyncio.sleep(PENDING_REPLY_DELAY_SECONDS)
    try:
        replies = await group_service.build_and_send_pending(chat_id)
        for reply_to_message_id, answer in replies:
            await bot.send_message(
                chat_id=chat_id,
                text=answer,
                reply_to_message_id=reply_to_message_id,
            )
            logger.info(
                "Delayed reply sent: chat_id=%s reply_to_message_id=%s answer='%s'",
                chat_id,
                reply_to_message_id,
                compact_log_text(answer, 700),
            )
    except Exception:
        logger.exception(
            "Delayed answer check failed: chat_id=%s",
            chat_id,
        )
