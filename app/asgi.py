"""Точка входа для uvicorn: `uvicorn app.asgi:app`.

Настройки берутся из окружения (`.env` рядом с репозиторием на локальной машине,
файл юнита на проде). Переключатель индексации по умолчанию закрыт — открыть его
можно только явной переменной, и только после подтверждения владельца.
"""
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.main import create_app  # noqa: E402

app = create_app()
