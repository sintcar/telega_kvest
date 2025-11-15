import asyncio
import datetime as dt
import traceback
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, FSInputFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db import AsyncSessionLocal
from . import models


# === ОТПРАВКА ВОПРОСА ===
async def send_question(bot, question: models.Question, session: AsyncSession):
    """Отправляет вопрос в чат с кнопками ответов, рейтинга и приглашения"""

    # Загружаем варианты ответов
    options_res = await session.execute(
        select(models.Option).where(models.Option.question_id == question.id)
    )
    options = options_res.scalars().all()

    if not options:
        print(f"⚠️ Вопрос {question.id} не имеет вариантов ответа — пропускаем")
        return

    # Кнопки с вариантами ответов
    buttons = [
        [InlineKeyboardButton(text=o.text, callback_data=f"answer:{question.id}:{o.id}")]
        for o in options
    ]

    # ➕ Добавляем кнопки "Рейтинг" и "Пригласить друга"
    buttons.append([
        InlineKeyboardButton(text="📊 Рейтинг", callback_data="show_rating"),
        InlineKeyboardButton(text="📨 Пригласить друга", callback_data="invite_friend"),
    ])

    markup = InlineKeyboardMarkup(inline_keyboard=buttons)

    try:
        # Отправляем сообщение с вопросом
        if question.image_path:
            photo_path = f"uploads/{question.image_path}"
            photo = FSInputFile(photo_path)
            msg = await bot.send_photo(
                chat_id=question.chat_id,
                photo=photo,
                caption=question.text,
                reply_markup=markup,
            )
        else:
            msg = await bot.send_message(
                chat_id=question.chat_id,
                text=question.text,
                reply_markup=markup,
            )

        # Фиксируем публикацию
        question.posted_at = dt.datetime.now()  # локальное время
        question.message_id = msg.message_id
        await session.commit()

        print(f"✅ Вопрос {question.id} отправлен в {question.chat_id}")

    except Exception as e:
        print(f"❌ Ошибка при отправке вопроса {question.id}: {e}")
        print(traceback.format_exc())


# === ПЛАНИРОВЩИК ===
async def scheduler_loop(bot):
    """Постоянно проверяет базу и отправляет новые вопросы"""
    print("🕒 Планировщик запущен, проверка каждые 60 секунд")

    while True:
        try:
            async with AsyncSessionLocal() as session:
                now = dt.datetime.now()
                print(f"[DEBUG] Проверка заданий: текущее ЛОКАЛЬНОЕ время {now.isoformat()}")

                # Отладка: вывод всех активных вопросов
                q_all = await session.execute(
                    select(models.Question).where(
                        models.Question.is_active.is_(True),
                        models.Question.chat_id.is_not(None),
                    )
                )
                all_questions = q_all.scalars().all()
                print(f"[DEBUG] Всего активных вопросов в базе: {len(all_questions)}")

                for q in all_questions:
                    print(
                        f"[DEBUG] ➤ ID={q.id}, scheduled_at={q.scheduled_at}, "
                        f"posted_at={q.posted_at}, chat_id={q.chat_id}"
                    )

                # Ищем те, что пора публиковать
                q_ready = await session.execute(
                    select(models.Question).where(
                        models.Question.scheduled_at <= now,
                        models.Question.posted_at.is_(None),
                        models.Question.is_active.is_(True),
                        models.Question.chat_id.is_not(None),
                    )
                )
                ready = q_ready.scalars().all()
                print(f"[DEBUG] Найдено для публикации: {len(ready)}")

                for question in ready:
                    await send_question(bot, question, session)

        except Exception as e:
            print(f"⚠️ Ошибка в планировщике: {e}")
            print(traceback.format_exc())

        await asyncio.sleep(60)
