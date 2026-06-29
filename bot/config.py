"""Configuration loading and validation."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional
import yaml


@dataclass
class MensaConfig:
    name: str
    url: str
    short_name: str


@dataclass
class MealTimesConfig:
    lunch_start: str = "11:00"
    lunch_end: str = "14:30"
    zwischenversorgung_start: str = "14:30"
    zwischenversorgung_end: str = "17:00"
    abendessen_start: str = "17:00"
    abendessen_end: str = "21:00"


@dataclass
class MatrixConfig:
    homeserver: str
    username: str
    room_id: str
    store_path: str
    password: Optional[str] = None
    access_token: Optional[str] = None
    device_name: str = "MensaBot"


@dataclass
class BotConfig:
    command_prefix: str = "!mensa"
    max_poll_mensas: int = 3
    vote_duration_minutes: int = 20
    cache_duration_minutes: int = 30
    timezone: str = "Europe/Berlin"
    db_path: str = "/data/mensa_bot.db"
    log_level: str = "INFO"
    voting_method: str = "approval"   # "borda", "irv", or "approval"
    daily_message_enabled: bool = False
    daily_message_time: str = "10:30"


@dataclass
class Config:
    matrix: MatrixConfig
    bot: BotConfig
    meal_times: MealTimesConfig
    mensas: list[MensaConfig]


def load_config(path: str) -> Config:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    m = raw["matrix"]
    matrix = MatrixConfig(
        homeserver=m["homeserver"],
        username=m["username"],
        room_id=m["room_id"],
        store_path=m.get("store_path", "/data/nio_store"),
        password=m.get("password"),
        access_token=m.get("access_token"),
        device_name=m.get("device_name", "MensaBot"),
    )

    if not matrix.password and not matrix.access_token:
        raise ValueError("config.yaml muss entweder 'password' oder 'access_token' enthalten.")

    b = raw.get("bot", {})
    voting_method = b.get("voting_method", "approval").lower()
    if voting_method not in ("borda", "irv", "approval"):
        raise ValueError(f"Ungültige voting_method: {voting_method!r}. Erlaubt: 'borda', 'irv', 'approval'.")
    bot = BotConfig(
        command_prefix=b.get("command_prefix", "!mensa"),
        max_poll_mensas=b.get("max_poll_mensas", 3),
        vote_duration_minutes=b.get("vote_duration_minutes", 20),
        cache_duration_minutes=b.get("cache_duration_minutes", 30),
        timezone=b.get("timezone", "Europe/Berlin"),
        db_path=b.get("db_path", "/data/mensa_bot.db"),
        log_level=b.get("log_level", "INFO"),
        voting_method=voting_method,
        daily_message_enabled=b.get("daily_message_enabled", False),
        daily_message_time=b.get("daily_message_time", "10:30"),
    )

    mt = raw.get("meal_times", {})
    meal_times = MealTimesConfig(
        lunch_start=mt.get("lunch_start", "11:00"),
        lunch_end=mt.get("lunch_end", "14:30"),
        zwischenversorgung_start=mt.get("zwischenversorgung_start", "14:30"),
        zwischenversorgung_end=mt.get("zwischenversorgung_end", "17:00"),
        abendessen_start=mt.get("abendessen_start", "17:00"),
        abendessen_end=mt.get("abendessen_end", "21:00"),
    )

    mensas = []
    for entry in raw.get("mensas", []):
        mensas.append(MensaConfig(
            name=entry["name"],
            url=entry["url"],
            short_name=entry.get("short_name", entry["name"]),
        ))

    if not mensas:
        raise ValueError("config.yaml muss mindestens eine Mensa enthalten.")

    return Config(matrix=matrix, bot=bot, meal_times=meal_times, mensas=mensas)
