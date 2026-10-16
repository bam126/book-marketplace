# Книжный маркетплейс

Учебный проект Куулара Санчая и Савельева Дмитрия по АИС. ЛР №2: контейнеры, JWT, API Gateway, Consul и балансировка. ЛР №3: заказы и получение связанных данных через GraphQL. История исходных работ сохранена.

## Запуск

Нужен запущенный Docker Desktop с Docker Compose. В PowerShell из корня проекта создайте `.env` **только при первом запуске**:

```powershell
if (!(Test-Path .env)) {
    $bytes = New-Object byte[] 48
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($bytes)
    $rng.Dispose()
    'SECRET_KEY=' + [Convert]::ToBase64String($bytes) | Set-Content .env -Encoding ascii
}
docker compose up --build -d --wait
docker compose ps
```

`.env` не включается в Git и Docker-образы. `.env.example` описывает обязательную переменную; значение-заглушку использовать нельзя.

| Компонент | Адрес |
|---|---|
| Auth Swagger | http://localhost:8080/api/auth/api-docs |
| Catalog Swagger | http://localhost:8080/api/catalog/api-docs |
| Order Swagger | http://localhost:8080/api/orders/api-docs |
| GraphQL | http://localhost:8080/graphql |
| Consul UI | http://localhost:8500/ui/ |

Опубликованы только Nginx (8080) и Consul (8500), на loopback. Остальные сервисы доступны внутри Docker-сети.

## Компоненты и файлы

- `auth_service/`: `main.py` — регистрация по email, вход и `/me`, JWT HS256, Passlib PBKDF2; `requirements.txt` — зависимости; `Dockerfile` — образ.
- `catalog_service/`: те же три файла для единой реализации CRUD товаров, валидации, пагинации и `instance_id`. Compose запускает один образ дважды с разными `INSTANCE_NAME`.
- `order_service/`: те же три файла для создания заказов и поиска по пользователю или ID.
- `graphql_gateway/`: те же три файла для объединения REST-данных заказов и товаров. URL зависимых сервисов передаются через окружение.
- `service_discovery.py`: регистрация пяти экземпляров приложений в Consul, HTTP health checks, повторные попытки и дерегистрация при завершении.
- `nginx/nginx.conf`: маршруты API, round-robin между Catalog и переключение при недоступности экземпляра.
- `docker-compose.yml`: семь контейнеров, сеть, проверки здоровья и настройки Consul.
- `.gitignore`, `.dockerignore`: исключения секретов, кэша и результатов тестов; `.gitattributes`: правила окончаний строк.
- `tests/integration.py`: реальные HTTP/Docker-проверки; `artifacts/` — локальные результаты, исключённые из Git.

Основные REST-префиксы: `/api/auth`, `/api/catalog`, `/api/orders`. Старые `/auth/` и `/catalog/` перенаправляются к соответствующим сервисам; схема данных соответствует ЛР №3: `email`, `access_token`, товар с `name`, `price`, `stock`.

## Проверки

Для автоматического прогона нужен Python 3 со стандартной библиотекой:

```powershell
python tests/integration.py
```

Тест временно останавливает приложения и пересоздаёт Consul. Выполняйте его на учебном стенде: данные сервисов хранятся в памяти и теряются при перезапуске. В конце тест восстанавливает семь контейнеров. Результаты: `artifacts/integration-results.json` и `artifacts/docker-compose-ps-final.txt`; секрет и полный JWT в отчёт не записываются.

Проверяются JWT и отказ без токена, CRUD, валидация и пагинация Catalog, создание/чтение Order, GraphQL с деталями товаров, балансировка, отказ/возврат экземпляра, регистрация и восстановление Consul.

Ручная проверка балансировки и отказа:

```powershell
1..10 | ForEach-Object { (Invoke-RestMethod http://localhost:8080/api/catalog/products).instance_id }
docker stop catalog-1
1..10 | ForEach-Object { (Invoke-RestMethod http://localhost:8080/api/catalog/products).instance_id }
docker start catalog-1
Start-Sleep 6
1..10 | ForEach-Object { (Invoke-RestMethod http://localhost:8080/api/catalog/products).instance_id }
```

Для демонстрации связки Order → GraphQL сначала выполните `docker stop catalog-2`, затем создайте товары через Catalog Swagger и заказ с их ID через Order Swagger. Запрос в GraphQL (подставьте `user_id` заказа):

```graphql
query {
  ordersByUserId(userId: "student@example.com") {
    id userId status
    items { productId quantity product { id name price stock } }
  }
}
```

После демонстрации: `docker start catalog-2`. Для остановки стенда: `docker compose down`.

## Ограничения учебной реализации

Catalog-экземпляры имеют независимые хранилища в памяти. Балансировка обеспечивает доступность HTTP, но не репликацию товаров. Поэтому связку заказов и товаров проверяем с одним активным Catalog; балансировку и отказ — отдельно с двумя. Общая БД потребует отдельного архитектурного решения.

JWT защищает `/api/auth/me`; Catalog, Order и GraphQL пока публичные. Order не резервирует остатки и не проверяет наличие товара. Отсутствующие связанные данные приводят к GraphQL `errors`, даже при HTTP 200. Пользователи, товары и заказы не переживают перезапуск своих контейнеров.

Consul работает в dev-режиме. Nginx использует явно заданные upstream и Docker DNS; каталог Consul автоматически не меняет конфигурацию Nginx.

## Совместная работа

`main` — проверенная версия. Текущая интеграция — `lab-3/integration`. Следующую лабораторную начинаем отдельной веткой от актуальной `main`, проверяем через PR и объединяем обычным merge с сохранением коммитов авторов. После принятия законченной лабораторной ставим тег `lab-2`, `lab-3` и далее на согласованный коммит. Полные копии проекта для каждой лабораторной не нужны.
