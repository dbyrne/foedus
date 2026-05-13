"""ORM models for foedus.web.

Naming note: avoid `Session` collision with sqlalchemy's Session — the
auth-session table is `SessionRow`.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import (
    String, Integer, Text, DateTime, ForeignKey, Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from foedus.web.db import Base

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    github_id: Mapped[Optional[int]] = mapped_column(Integer, unique=True, nullable=True)
    github_login: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class Game(Base):
    __tablename__ = "games"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # pending|active|finished
    map_seed: Mapped[int] = mapped_column(Integer, nullable=False)
    map_preset: Mapped[str] = mapped_column(String(64), nullable=False)
    max_turns: Mapped[int] = mapped_column(Integer, nullable=False)
    phase_deadline_hours: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    current_phase_deadline_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    discord_webhook_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    state_json: Mapped[str] = mapped_column(Text, nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    seats: Mapped[list["GameSeat"]] = relationship(back_populates="game",
                                                   cascade="all, delete-orphan")
    chats: Mapped[list["ChatMessage"]] = relationship(back_populates="game",
                                                     cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_games_status_deadline", "status", "current_phase_deadline_at"),
    )

class GameSeat(Base):
    __tablename__ = "game_seats"
    game_id: Mapped[str] = mapped_column(ForeignKey("games.id"), primary_key=True)
    player_idx: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(8), nullable=False)  # human|bot
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    bot_class: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    game: Mapped[Game] = relationship(back_populates="seats")

    __table_args__ = (
        Index("ix_game_seats_user", "user_id"),
    )

class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[str] = mapped_column(ForeignKey("games.id"))
    turn: Mapped[int] = mapped_column(Integer, nullable=False)
    sender_idx: Mapped[int] = mapped_column(Integer, nullable=False)
    recipients_mask: Mapped[int] = mapped_column(Integer, nullable=False)  # -1 = broadcast
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    game: Mapped[Game] = relationship(back_populates="chats")

class SessionRow(Base):
    __tablename__ = "sessions"
    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
