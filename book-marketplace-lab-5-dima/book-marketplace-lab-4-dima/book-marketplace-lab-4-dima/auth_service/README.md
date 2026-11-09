# Auth Service

REST API для аутентификации пользователей.

## Эндпоинты

- `POST /api/auth/register` — регистрация (email, password)
- `POST /api/auth/login` — вход, возвращает JWT-токен
- `GET /api/auth/me` — получить данные текущего пользователя (требует токен)

## Запуск

```bash
pip install -r requirements.txt
python -m uvicorn main:app --reload --port 8001