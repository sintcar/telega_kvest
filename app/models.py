import datetime as dt
from sqlalchemy import (
    Integer,
    BigInteger,
    String,
    DateTime,
    Boolean,
    ForeignKey,
    Text,
    Float,
)
from sqlalchemy.orm import relationship, Mapped, mapped_column
from .db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    joined_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)

    # 🔗 Новый функционал — система рефералов
    referrer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    ref_bonus: Mapped[float] = mapped_column(Float, default=0)  # бонусы за приглашения

    # Связь на того, кто пригласил
    referrer: Mapped["User"] = relationship(
        "User", remote_side=[id], back_populates="referrals"
    )

    # Связь на приглашённых пользователей
    referrals: Mapped[list["User"]] = relationship(
        "User", back_populates="referrer", cascade="all, delete-orphan"
    )

    # Существующие связи
    attempts: Mapped[list["Attempt"]] = relationship(
        "Attempt", back_populates="user", cascade="all, delete-orphan"
    )


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    scheduled_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    posted_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    image_path: Mapped[str | None] = mapped_column(String(255), nullable=True)

    options: Mapped[list["Option"]] = relationship(
        "Option", back_populates="question", cascade="all, delete-orphan"
    )
    attempts: Mapped[list["Attempt"]] = relationship(
        "Attempt", back_populates="question", cascade="all, delete-orphan"
    )


class Option(Base):
    __tablename__ = "options"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE")
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False)

    question: Mapped["Question"] = relationship("Question", back_populates="options")
    attempts: Mapped[list["Attempt"]] = relationship(
        "Attempt", back_populates="option", cascade="all, delete-orphan"
    )


class Attempt(Base):
    __tablename__ = "attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"))
    option_id: Mapped[int] = mapped_column(ForeignKey("options.id", ondelete="CASCADE"))
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False)
    answered_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=dt.datetime.utcnow, index=True
    )

    user: Mapped["User"] = relationship("User", back_populates="attempts")
    question: Mapped["Question"] = relationship("Question", back_populates="attempts")
    option: Mapped["Option"] = relationship("Option", back_populates="attempts")
