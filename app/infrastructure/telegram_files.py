from __future__ import annotations

from pathlib import Path

from aiogram import Bot

from app.utils.files import create_temp_path


async def download_telegram_file(bot: Bot, file_id: str, suffix: str, temp_dir: Path) -> Path:
    file = await bot.get_file(file_id)
    destination = create_temp_path(suffix=suffix, temp_dir=temp_dir)
    await bot.download(file, destination=destination)
    return destination
