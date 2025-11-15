import datetime as dt
from typing import Optional

from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from .db import AsyncSessionLocal
from . import models

router = Router()


# === УТИЛИТЫ ===

async def get_or_create_user(session: AsyncSession, tg_user) -> models.User:
    """Создаёт или возвращает пользователя"""
    q = await session.execute(
        select(models.User).where(models.User.telegram_id == tg_user.id)
    )
    user = q.scalar_one_or_none()
    if not user:
        user = models.User(
            telegram_id=tg_user.id,
            username=tg_user.username,
            first_name=tg_user.first_name,
            last_name=tg_user.last_name,
            ref_bonus=0,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


async def add_referral_bonus(session: AsyncSession, referrer_id: int):
    """Начисляем +200 очков за приглашённого"""
    ref_user = await session.get(models.User, referrer_id)
    if ref_user:
        if not hasattr(ref_user, "ref_bonus") or ref_user.ref_bonus is None:
            ref_user.ref_bonus = 0
        ref_user.ref_bonus += 200
        await session.commit()


# === КОМАНДЫ ===

@router.message(CommandStart())
async def cmd_start(message: Message):
    """Приветствие с кнопками и поддержкой реферальных ссылок"""
    async with AsyncSessionLocal() as session:
        args = message.text.split()
        referrer_id = None

        # Проверяем, пришёл ли код приглашения
        if len(args) > 1 and args[1].startswith("ref"):
            try:
                referrer_id = int(args[1][3:])
            except ValueError:
                referrer_id = None

        user = await get_or_create_user(session, message.from_user)

        # Если новый и есть пригласивший
        inviter_name = None
        if referrer_id and not getattr(user, "referrer_id", None) and user.id != referrer_id:
            user.referrer_id = referrer_id
            await add_referral_bonus(session, referrer_id)
            await session.commit()

            res = await session.execute(select(models.User).where(models.User.id == referrer_id))
            inviter = res.scalar_one_or_none()
            if inviter:
                inviter_name = inviter.first_name or inviter.username or str(inviter.telegram_id)

    # === Текст приветствия ===
    text = (
        "Привет! 👋\n\n"
        "Добро пожаловать в <b>Онлайн квест Тайна!</b> 🕵️‍♀️\n"
        "Отвечай на вопросы и зарабатывай очки!\n"
        "По итогам игроки с лучшими результатами получат призы 🎁\n\n"
        "Если готов — жми <b>«В квест!»</b>!\n"
        "Но не забудь сначала посмотреть правила 👇"
    )

    if inviter_name:
        text = f"🎉 Тебя пригласил {inviter_name}!\n\n" + text

    # === Кнопки ===
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="🚀 В квест!",
            url="https://t.me/kvest04"  # 🔗 ← замени на ссылку на свою группу квеста
        )
    )
    builder.row(
        InlineKeyboardButton(text="📜 Правила", callback_data="show_rules"),
        InlineKeyboardButton(text="🏆 Призы", callback_data="show_prizes"),
    )

    await message.answer(text, parse_mode="HTML", reply_markup=builder.as_markup())


# === Кнопки из приветственного меню ===

@router.callback_query(F.data == "show_rules")
async def show_rules(callback: CallbackQuery):
    """Показывает правила квеста"""
    rules_text = (
        "📜 <b>Правила квеста</b>\n\n"
        "1️⃣ Каждый день публикуются новые вопросы.\n"
        "2️⃣ Отвечай быстрее других — за скорость начисляются бонусы!\n"
        "3️⃣ За правильный ответ: +100 баллов.\n"
        "4️⃣ За ошибку: -30 баллов.\n"
        "5️⃣ За приглашённого друга: +200 баллов.\n\n"
        "⚠️ На каждый вопрос можно ответить только один раз."
    )
    await callback.message.answer(rules_text, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "show_prizes")
async def show_prizes(callback: CallbackQuery):
    """Показывает список призов"""
    prizes_text = (
        "🎁 <b>Призы квеста «Тайна»</b>\n\n"
        "🥇 1 место — Смарт-часы\n"
        "🥈 2 место — Сертификат на 3000 ₽\n"
        "🥉 3 место — Подарочный набор сюрпризов\n\n"
        "🏅 Также бонусы и сюрпризы для активных участников!"
    )
    await callback.message.answer(prizes_text, parse_mode="HTML")
    await callback.answer()


# === СИСТЕМА ОЧКОВ ===

def compute_score(delta_seconds: float, wrong_attempts: int) -> float:
    """+100 за правильный, -30 за ошибку, бонус за скорость"""
    score = 100 - wrong_attempts * 30

    # бонус за скорость — первые 20 секунд +100, потом уменьшается на 0.5/мин
    if delta_seconds <= 20:
        score += 100
    else:
        penalty_minutes = (delta_seconds - 20) / 60
        bonus = max(100 - penalty_minutes * 0.5, 0)
        score += bonus

    return max(score, 0)


async def calculate_rating(session: AsyncSession):
    """Рассчёт рейтинга игроков"""
    subq = (
        select(
            models.Attempt.user_id,
            models.Attempt.question_id,
            func.min(models.Attempt.answered_at).label("first_correct_at"),
        )
        .where(models.Attempt.is_correct == True)
        .group_by(models.Attempt.user_id, models.Attempt.question_id)
        .subquery()
    )

    join_q = (
        select(
            models.User.id.label("user_id"),
            models.User.telegram_id,
            models.User.username,
            models.User.first_name,
            models.User.ref_bonus,
            models.Question.id.label("question_id"),
            models.Question.posted_at,
            subq.c.first_correct_at,
        )
        .join(subq, subq.c.user_id == models.User.id)
        .join(models.Question, models.Question.id == subq.c.question_id)
    )

    res = await session.execute(join_q)
    rows = res.mappings().all()
    if not rows:
        return []

    scores = {}
    for row in rows:
        uid = row["user_id"]
        posted_at = row["posted_at"]
        first_correct = row["first_correct_at"]

        if not posted_at or not first_correct:
            continue

        delta = (first_correct - posted_at).total_seconds()
        attempts_res = await session.execute(
            select(models.Attempt).where(
                models.Attempt.user_id == uid,
                models.Attempt.question_id == row["question_id"],
                models.Attempt.answered_at <= first_correct,
            )
        )
        attempts = attempts_res.scalars().all()
        wrong = sum(1 for a in attempts if not a.is_correct)
        correct = 1 if any(a.is_correct for a in attempts) else 0
        score = compute_score(delta, wrong)

        if uid not in scores:
            scores[uid] = {
                "user_id": uid,
                "telegram_id": row["telegram_id"],
                "username": row["username"],
                "first_name": row["first_name"],
                "score": 0.0,
                "correct": 0,
                "wrong": 0,
                "ref_bonus": row["ref_bonus"] or 0,
                "times": [],
            }

        scores[uid]["score"] += score
        scores[uid]["correct"] += correct
        scores[uid]["wrong"] += wrong
        scores[uid]["times"].append(delta)

    # добавляем реферальные бонусы
    for s in scores.values():
        s["score"] += s["ref_bonus"]
        if s["times"]:
            s["avg_time"] = sum(s["times"]) / len(s["times"])
        else:
            s["avg_time"] = 0.0

    rating = sorted(scores.values(), key=lambda x: x["score"], reverse=True)
    return rating


# === РЕЙТИНГ ===

@router.message(Command("rating"))
async def cmd_rating(message: Message):
    """Команда /rating — показывает рейтинг игрока"""
    async with AsyncSessionLocal() as session:
        rating = await calculate_rating(session)
        user = await get_or_create_user(session, message.from_user)

    if not rating:
        await message.answer("Рейтинг пока пуст 🤷‍♂️")
        return

    user_place = None
    user_data = None
    for i, r in enumerate(rating, start=1):
        if r["telegram_id"] == user.telegram_id:
            user_place = i
            user_data = r
            break

    text = "🏆 <b>Рейтинг игроков</b>\n\n"
    if user_data:
        text += (
            f"👤 <b>{user_data.get('first_name') or user.username or user.telegram_id}</b>\n"
            f"Место: <b>{user_place}</b>\n"
            f"Очки: <b>{round(user_data['score'], 1)}</b>\n"
            f"✅ {user_data['correct']} | ❌ {user_data['wrong']}\n"
            f"💰 Бонусы за друзей: +{user_data['ref_bonus']}\n"
            f"⏱ Среднее время: {round(user_data['avg_time'], 1)} сек\n\n"
        )
    else:
        text += "Ты ещё не участвовал 😅\n\n"

    text += "📋 <b>Топ-10 игроков:</b>\n"
    for i, r in enumerate(rating[:10], start=1):
        name = r["username"] or r["first_name"] or str(r["telegram_id"])
        text += f"{i}. {name} — {int(r['score'])} очков\n"

    await message.answer(text, parse_mode="HTML")


# === ОБРАБОТКА ВЫБОРА ОТВЕТОВ ===

@router.callback_query(F.data.startswith("answer:"))
async def on_answer(callback: CallbackQuery):
    """Обработка выбора ответа"""
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("Некорректные данные.", show_alert=True)
        return

    _, q_id_str, opt_id_str = parts
    try:
        question_id = int(q_id_str)
        option_id = int(opt_id_str)
    except ValueError:
        await callback.answer("Некорректные данные.", show_alert=True)
        return

    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, callback.from_user)

        # Проверяем, нет ли уже правильного ответа
        existing_correct_res = await session.execute(
            select(models.Attempt).where(
                models.Attempt.user_id == user.id,
                models.Attempt.question_id == question_id,
                models.Attempt.is_correct == True,
            )
        )
        existing_correct = existing_correct_res.scalar_one_or_none()
        if existing_correct:
            await callback.answer("✅ Вы уже правильно ответили на этот вопрос.", show_alert=True)
            return

        stmt = (
            select(models.Option, models.Question)
            .join(models.Question, models.Question.id == models.Option.question_id)
            .where(models.Option.id == option_id, models.Question.id == question_id)
        )
        res = await session.execute(stmt)
        row = res.first()
        if not row:
            await callback.answer("Вопрос не найден.", show_alert=True)
            return

        option: models.Option = row[0]
        question: models.Question = row[1]

        attempt = models.Attempt(
            user_id=user.id,
            question_id=question.id,
            option_id=option.id,
            is_correct=option.is_correct,
        )
        session.add(attempt)
        await session.commit()

        if option.is_correct:
            await callback.answer("✅ Правильно!", show_alert=True)
        else:
            await callback.answer("❌ Неправильно, попробуй ещё!", show_alert=True)
