# Книжный маркетплейс

Учебный проект по дисциплине «Архитектура информационных систем», ТПУ.
Авторы: Куулар Санчай и Савельев Дмитрий, группа 8И41.

Маркетплейс позволяет зарегистрироваться, работать с каталогом книг и создавать заказы.

В **ЛР №2** добавлены запуск в Docker Compose, вход по JWT, Nginx, регистрация сервисов в Consul, балансировка между двумя экземплярами Catalog и переключение при отказе одного из них.

В **ЛР №3** добавлены заказы и GraphQL для получения заказов вместе с данными о книгах.

В **ЛР №4** добавлена Saga через RabbitMQ: Order создаёт заказ, Payment имитирует оплату, Notification пишет уведомление в лог. При ошибке оплаты заказ отменяется. Заказы и ожидающие отправки события сохраняются в SQLite.

В **ЛР №5** добавлен gRPC-интерфейс PaymentService с методом CheckPaymentStatus. Order обращается к Payment через gRPC-клиент с таймаутом 3 секунды. Circuit Breaker открывается после трёх последовательных ошибок и через 10 секунд разрешает пробный вызов. При ошибке или открытой цепи возвращается fallback со статусом PROCESSING. Флаг simulate_failure позволяет управляемо имитировать недоступность Payment.

## Сервисы

- **Auth** — регистрация пользователей, вход и проверка JWT.
- **Catalog** — добавление, просмотр, изменение и удаление книг.
- **Order** — создание и просмотр заказов.
- **Payment** — имитация оплаты через события Saga и gRPC-метод проверки оплаты.
- **Notification** — журнал уведомлений об оплате и отмене заказа.
- **RabbitMQ** — передача событий между сервисами.
- **GraphQL Gateway** — получение связанных данных из Order и Catalog.
- **Nginx** — общий вход в API и распределение запросов к Catalog.
- **Consul** — регистрация сервисов и проверка их доступности.

## Запуск

Запустите Docker Desktop. В PowerShell из папки проекта выполните команды ниже. Они создадут `.env` со случайным секретным ключом, только если файла ещё нет, и запустят проект.

```powershell
if (!(Test-Path .env)) {
    $bytes = New-Object byte[] 48
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($bytes)
    $rng.Dispose()
    'SECRET_KEY=' + [Convert]::ToBase64String($bytes) | Set-Content .env -Encoding ascii
}
if (!(Select-String -Path .env -Pattern '^RABBITMQ_USER=' -Quiet)) {
    'RABBITMQ_USER=student' | Add-Content .env -Encoding ascii
}
if (!(Select-String -Path .env -Pattern '^RABBITMQ_PASSWORD=' -Quiet)) {
    $bytes = New-Object byte[] 32
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($bytes)
    $rng.Dispose()
    'RABBITMQ_PASSWORD=' + [Convert]::ToBase64String($bytes) | Add-Content .env -Encoding ascii
}
docker compose up --build -d --wait
```

Файл `.env` хранится только локально и исключён из Git. Не отправляйте его другим людям и не добавляйте в репозиторий.

## Где открыть

- [Auth Swagger](http://localhost:8080/api/auth/api-docs)
- [Catalog Swagger](http://localhost:8080/api/catalog/api-docs)
- [Order Swagger](http://localhost:8080/api/orders/api-docs)
- [GraphQL](http://localhost:8080/graphql)
- [Consul](http://localhost:8500/ui/)
- [RabbitMQ Management](http://localhost:18072/)

Остановка проекта: `docker compose down`.

## Проверка ЛР №5

Откройте [Order Swagger](http://localhost:8080/api/orders/api-docs), раздел Payment, метод:

`GET /api/orders/{order_id}/payment-status`

Параметры: `order_id=lab5-order-1`, `amount=500`.

1. С `simulate_failure=false` выполните несколько запросов: ожидаются SUCCESS и CLOSED.
2. Переключите `simulate_failure=true` и выполните три запроса подряд: ожидаются PROCESSING и OPEN.
3. До истечения 10 секунд повторите запрос: вернётся fallback без обращения к Payment.
4. После ожидания более 10 секунд установите `simulate_failure=false` и выполните запрос: успешная проба закроет цепь.

Переходы состояний можно посмотреть в PowerShell:

```powershell
docker compose logs --no-color --since 30m order 2>&1 |
    Select-String "Circuit Breaker"
```

Ожидаемая последовательность: CLOSED → OPEN → HALF-OPEN → CLOSED.

Контракт находится в `contracts/payment.proto`, клиент — в `payment_client.py`, Circuit Breaker и fallback — в `payment_breaker.py`, сервер — в `payment_service/gRPC_server.py`.

Проверка оплаты демонстрационная: реальные деньги не списываются, статус заказа в SQLite этим методом не изменяется. Fallback PROCESSING не запускает фоновую оплату.

**Ограничение:** пользователи и товары хранятся в памяти и теряются при перезапуске. Заказы сохраняются в Docker volume SQLite; не используйте `docker compose down -v`, если хотите сохранить данные. У двух экземпляров Catalog нет общей базы данных. Для демонстрации заказов с данными о книгах сначала остановите второй экземпляр командой `docker stop catalog-2`, затем создавайте книги и заказы. После демонстрации верните его командой `docker start catalog-2`.
