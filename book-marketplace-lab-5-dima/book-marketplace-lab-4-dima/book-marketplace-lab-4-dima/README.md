# Книжный маркетплейс

Учебный проект по дисциплине «Архитектура информационных систем», ТПУ.
Авторы: Куулар Санчай и Савельев Дмитрий, группа 8И41.

Маркетплейс позволяет зарегистрироваться, работать с каталогом книг и создавать заказы.

В **ЛР №2** добавлены запуск в Docker Compose, вход по JWT, Nginx, регистрация сервисов в Consul, балансировка между двумя экземплярами Catalog и переключение при отказе одного из них.

В **ЛР №3** добавлены заказы и GraphQL для получения заказов вместе с данными о книгах.

## Сервисы

- **Auth** — регистрация пользователей, вход и проверка JWT.
- **Catalog** — добавление, просмотр, изменение и удаление книг.
- **Order** — создание и просмотр заказов.
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
docker compose up --build -d --wait
```

Файл `.env` хранится только локально и исключён из Git. Не отправляйте его другим людям и не добавляйте в репозиторий.

## Где открыть

- [Auth Swagger](http://localhost:8080/api/auth/api-docs)
- [Catalog Swagger](http://localhost:8080/api/catalog/api-docs)
- [Order Swagger](http://localhost:8080/api/orders/api-docs)
- [GraphQL](http://localhost:8080/graphql)
- [Consul](http://localhost:8500/ui/)

Остановка проекта: `docker compose down`.

**Ограничение:** данные хранятся в памяти и теряются при перезапуске. У двух экземпляров Catalog нет общей базы данных. Для демонстрации заказов с данными о книгах сначала остановите второй экземпляр командой `docker stop catalog-2`, затем создавайте книги и заказы. После демонстрации верните его командой `docker start catalog-2`.
