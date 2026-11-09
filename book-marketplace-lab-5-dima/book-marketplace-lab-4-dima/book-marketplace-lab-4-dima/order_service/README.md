# Order Service

Сервис для создания и просмотра заказов.

## Возможности

- Создание заказа
- Получение заказа по ID
- Просмотр заказов пользователя

## API

- POST /api/orders — создать заказ
- GET /api/orders/{order_id} — получить заказ
- GET /api/orders?user_id=... — заказы пользователя

## Проверка

Swagger: http://localhost:8080/api/orders/api-docs