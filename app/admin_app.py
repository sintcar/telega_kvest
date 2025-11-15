import datetime as dt
import os
from typing import Optional

from fastapi import FastAPI, Request, Form, Depends, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .db import get_session, init_db
from . import models
from .handlers import calculate_rating

app = FastAPI(title="Quest Bot Admin")

app.add_middleware(
    SessionMiddleware, secret_key=settings.secret_key, session_cookie="quest_admin"
)

templates = Jinja2Templates(directory="app/templates")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")


@app.on_event("startup")
async def on_startup():
    await init_db()


# --- Авторизация администратора ---
def is_admin(request: Request) -> bool:
    return bool(request.session.get("admin"))


def require_admin(request: Request):
    if not is_admin(request):
        return RedirectResponse(url="/login", status_code=302)
    return None


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@app.post("/login", response_class=HTMLResponse)
async def login_submit(request: Request, password: str = Form(...)):
    if password == settings.admin_password:
        request.session["admin"] = True
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": "Неверный пароль"},
    )


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=302)


# --- Главная панель ---
@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    redirect = require_admin(request)
    if redirect:
        return redirect
    return templates.TemplateResponse("dashboard.html", {"request": request})


# --- Список вопросов ---
@app.get("/questions", response_class=HTMLResponse)
async def questions_list(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    redirect = require_admin(request)
    if redirect:
        return redirect

    stmt = select(models.Question).order_by(models.Question.scheduled_at, models.Question.id)
    res = await session.execute(stmt)
    questions = res.scalars().all()
    return templates.TemplateResponse(
        "questions_list.html", {"request": request, "questions": questions}
    )


# --- Создание вопроса ---
@app.get("/questions/new", response_class=HTMLResponse)
async def questions_new(request: Request):
    redirect = require_admin(request)
    if redirect:
        return redirect
    return templates.TemplateResponse(
        "question_form.html",
        {
            "request": request,
            "question": None,
            "options": ["", "", "", ""],
            "scheduled_at": "",
            "chat_id": settings.group_chat_id or "",
            "correct_index": 1,
        },
    )


@app.post("/questions/new", response_class=HTMLResponse)
async def questions_new_submit(
    request: Request,
    text: str = Form(...),
    scheduled_at: str = Form(""),
    chat_id: str = Form(""),
    option1: str = Form(""),
    option2: str = Form(""),
    option3: str = Form(""),
    option4: str = Form(""),
    correct_option: int = Form(1),
    image: UploadFile | None = File(None),
    session: AsyncSession = Depends(get_session),
):
    redirect = require_admin(request)
    if redirect:
        return redirect

    # --- Обработка загрузки картинки ---
    image_path = None
    if image and image.filename:
        os.makedirs("uploads", exist_ok=True)
        filename = f"{int(dt.datetime.utcnow().timestamp())}_{image.filename}"
        filepath = os.path.join("uploads", filename)
        with open(filepath, "wb") as f:
            f.write(await image.read())
        image_path = filename

    sched_dt: Optional[dt.datetime] = None
    if scheduled_at:
        try:
            sched_dt = dt.datetime.fromisoformat(scheduled_at)
        except ValueError:
            sched_dt = None

    q = models.Question(
        text=text,
        scheduled_at=sched_dt,
        chat_id=int(chat_id) if chat_id else None,
        image_path=image_path,
    )
    session.add(q)
    await session.flush()

    options_text = [option1, option2, option3, option4]
    for idx, opt_text in enumerate(options_text, start=1):
        if not opt_text.strip():
            continue
        session.add(
            models.Option(
                question_id=q.id,
                text=opt_text.strip(),
                is_correct=(idx == int(correct_option)),
            )
        )

    await session.commit()
    return RedirectResponse(url="/questions", status_code=302)


# --- Редактирование вопроса ---
@app.get("/questions/{qid}", response_class=HTMLResponse)
async def question_edit(
    request: Request,
    qid: int,
    session: AsyncSession = Depends(get_session),
):
    redirect = require_admin(request)
    if redirect:
        return redirect

    res = await session.execute(
        select(models.Question).where(models.Question.id == qid)
    )
    question = res.scalar_one_or_none()
    if not question:
        return RedirectResponse(url="/questions", status_code=302)

    options = question.options
    options_text = [o.text for o in options] + ["", "", "", ""]
    options_text = options_text[:4]
    correct_index = 1
    for idx, opt in enumerate(options, start=1):
        if opt.is_correct:
            correct_index = idx
            break

    scheduled_at = (
        question.scheduled_at.isoformat(timespec="minutes")
        if question.scheduled_at
        else ""
    )

    return templates.TemplateResponse(
        "question_form.html",
        {
            "request": request,
            "question": question,
            "options": options_text,
            "scheduled_at": scheduled_at,
            "chat_id": question.chat_id or settings.group_chat_id or "",
            "correct_index": correct_index,
        },
    )


@app.post("/questions/{qid}", response_class=HTMLResponse)
async def question_edit_submit(
    request: Request,
    qid: int,
    text: str = Form(...),
    scheduled_at: str = Form(""),
    chat_id: str = Form(""),
    option1: str = Form(""),
    option2: str = Form(""),
    option3: str = Form(""),
    option4: str = Form(""),
    correct_option: int = Form(1),
    is_active: Optional[str] = Form(None),
    image: UploadFile | None = File(None),
    session: AsyncSession = Depends(get_session),
):
    redirect = require_admin(request)
    if redirect:
        return redirect

    res = await session.execute(
        select(models.Question).where(models.Question.id == qid)
    )
    question = res.scalar_one_or_none()
    if not question:
        return RedirectResponse(url="/questions", status_code=302)

    question.text = text
    question.is_active = bool(is_active)

    # --- Обработка загрузки картинки ---
    if image and image.filename:
        os.makedirs("uploads", exist_ok=True)
        filename = f"{int(dt.datetime.utcnow().timestamp())}_{image.filename}"
        filepath = os.path.join("uploads", filename)
        with open(filepath, "wb") as f:
            f.write(await image.read())
        question.image_path = filename

    sched_dt: Optional[dt.datetime] = None
    if scheduled_at:
        try:
            sched_dt = dt.datetime.fromisoformat(scheduled_at)
        except ValueError:
            sched_dt = None
    question.scheduled_at = sched_dt
    question.chat_id = int(chat_id) if chat_id else None

    # Удаляем старые опции и создаём новые
    for opt in list(question.options):
        await session.delete(opt)

    await session.flush()

    options_text = [option1, option2, option3, option4]
    for idx, opt_text in enumerate(options_text, start=1):
        if not opt_text.strip():
            continue
        session.add(
            models.Option(
                question_id=question.id,
                text=opt_text.strip(),
                is_correct=(idx == int(correct_option)),
            )
        )

    await session.commit()
    return RedirectResponse(url="/questions", status_code=302)


# --- Пользователи ---
@app.get("/users", response_class=HTMLResponse)
async def users_list(request: Request, session: AsyncSession = Depends(get_session)):
    redirect = require_admin(request)
    if redirect:
        return redirect

    try:
        result = await session.execute(
            select(models.User).order_by(models.User.joined_at.desc())
        )
        users = result.scalars().all()
    except Exception as e:
        return HTMLResponse(f"<h3>Ошибка при получении пользователей: {e}</h3>", status_code=500)

    html = """
    <h1>Пользователи</h1>
    <a href='/'>← Назад</a><br><br>
    <table border='1' cellpadding='5' cellspacing='0'>
      <tr><th>ID</th><th>Имя</th><th>Username</th><th>Дата регистрации</th></tr>
    """
    for u in users:
        html += f"<tr><td>{u.id}</td><td>{u.first_name or ''} {u.last_name or ''}</td><td>{u.username or ''}</td><td>{u.joined_at}</td></tr>"
    html += "</table>"
    return HTMLResponse(content=html)


# --- Рейтинг пользователей ---
@app.get("/rating", response_class=HTMLResponse)
async def rating_page(request: Request, session: AsyncSession = Depends(get_session)):
    redirect = require_admin(request)
    if redirect:
        return redirect

    try:
        rating = await calculate_rating(session)
    except Exception as e:
        return HTMLResponse(f"<h3>Ошибка при расчёте рейтинга: {e}</h3>", status_code=500)

    html = """
    <h1>Рейтинг пользователей</h1>
    <a href='/'>← Назад</a><br><br>
    <table border='1' cellpadding='5' cellspacing='0'>
      <tr>
        <th>#</th>
        <th>Имя</th>
        <th>Username</th>
        <th>Очки</th>
        <th>✅ Правильных</th>
        <th>❌ Ошибок</th>
      </tr>
    """
    for i, r in enumerate(rating, start=1):
        first_name = r.get("first_name", "") or ""
        username = r.get("username", "") or r.get("telegram_id", "")
        score = round(r.get("score", 0), 1)
        correct = r.get("correct", 0)
        wrong = r.get("wrong", 0)

        html += f"""
        <tr>
            <td>{i}</td>
            <td>{first_name}</td>
            <td>{username}</td>
            <td>{score}</td>
            <td>{correct}</td>
            <td>{wrong}</td>
        </tr>
        """

    html += "</table>"
    return HTMLResponse(content=html)
