"""Smoke-тест базовой структуры нового FastAPI проекта."""


def test_app_imports() -> None:
    """Проверяет, что FastAPI app и Telegram router импортируются."""
    from app.api.routers.telegram import router
    from app.main import app

    assert app.title == "admin_bot"
    assert router.prefix == "/telegram"
