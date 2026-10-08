# Книжный маркетплейс — ЛР №2 по АИС

Совместная работа Куулара Санчая и Савельева Дмитрия. Исходные Auth и Catalog — вклад Дмитрия, сохранённый в коммите `b39db29`. Инфраструктура разрабатывается в `infra/nginx-consul`, без изменения истории `main`.

Цель: запустить микросервисы в Docker, показать регистрацию в Consul, маршрутизацию и балансировку через Nginx, проверить отказ одного экземпляра каталога.

## Архитектура

```text
Клиент -> localhost:8080 -> Nginx
                           | /auth/*    -> auth:8001
                           | /catalog/* -> catalog-1:8002
                           |            -> catalog-2:8003

auth, catalog-1, catalog-2 -> Consul HTTP API (consul:8500)
Consul -> /health каждого сервиса, каждые 5 секунд
Consul UI -> localhost:8500/ui/
```

Все контейнеры находятся в сети `marketplace`. Только Nginx (8080) и Consul (8500) опубликованы на `127.0.0.1`. У Auth и Catalog нет опубликованных портов. Оба Catalog используют один образ `book-marketplace-catalog:lab2`; сборка объявлена у `catalog-1`, а `catalog-2` использует готовый локальный образ (`pull_policy: never`).

- **Auth:** `/register`, `/login`, `/me`; пользователи в памяти, пароли — Passlib PBKDF2-SHA256 (600 000 итераций, случайная соль), JWT HS256 с ограниченным сроком действия. `SECRET_KEY` обязателен через окружение, стандартного рабочего ключа в коде нет.
- **Catalog:** CRUD `/products`, поле `instance_id` из `INSTANCE_NAME`. Хранилища двух процессов независимы. После перезапуска процесса его товары теряются.
- **Nginx:** удаляет префиксы `/auth/` и `/catalog/`; равномерно распределяет запросы по двум Catalog. При ошибке соединения пробует другой upstream (`max_fails=1`, `fail_timeout=5s`, максимум две попытки). Автоматический повтор уже отправленных POST не включён.
- **Consul:** сервисы регистрируются через FastAPI lifespan и HTTP API; при штатной остановке удаляют регистрацию. Фоновая проверка регистрации с повторными попытками до 10 секунд позволяет запустить Consul позже и восстановить регистрацию после его перезапуска. Проверки здоровья выполняются каждые 5 секунд, timeout — 2 секунды.

**Nginx не получает адреса из Consul.** Состав upstream задан в конфигурации, IP-адреса имён контейнеров обновляются через Docker DNS. Consul — отдельный реестр и монитор здоровья. Consul работает в учебном dev-режиме без ACL и постоянного хранения. Отказоустойчивость показана для чтения каталога при отказе одного экземпляра; Nginx и Auth остаются одиночными компонентами. Это не production-конфигурация и не репликация данных.

## Структура

```text
auth_service/       main.py, requirements.txt, Dockerfile
catalog_service/    main.py, requirements.txt, Dockerfile
nginx/nginx.conf
service_discovery.py
docker-compose.yml
.dockerignore
.gitignore
.env.example
tests/integration.py
evidence/
README.md
DEFENSE_GUIDE.md
```

## Запуск (PowerShell)

Нужен запущенный Docker Desktop в режиме Linux containers. Команды выполняются в корне проекта. Создать секрет один раз; существующий `.env` команда не перезаписывает:

```powershell
Set-Location 'C:\Users\qw\Desktop\Учеба\АИС\book-marketplace-lab2'
if (-not (Test-Path .env)) {
    $bytes = New-Object byte[] 48
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($bytes)
    $rng.Dispose()
    'SECRET_KEY=' + [Convert]::ToBase64String($bytes) | Set-Content .env -Encoding ascii
}
docker --version
docker info
docker compose version
docker compose up --build -d
docker compose up -d --wait
docker compose ps
```

Не использовать строку-заглушку из `.env.example` как секрет. `.env` исключён из Git и Docker build context. Не публиковать `docker compose config` без `--quiet`: полный вывод содержит подставленный секрет.

Адреса:

- Gateway: http://localhost:8080
- Auth Swagger: http://localhost:8080/auth/docs
- Catalog Swagger: http://localhost:8080/catalog/docs
- Consul UI: http://localhost:8500/ui/

## Auth / JWT

```powershell
$base = 'http://localhost:8080'
$user = @{username=('demo_' + [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()); password='Demo-password-123!'}
$json = $user | ConvertTo-Json
Invoke-RestMethod "$base/auth/register" -Method Post -ContentType 'application/json' -Body $json
$login = Invoke-RestMethod "$base/auth/login" -Method Post -ContentType 'application/json' -Body $json
$headers = @{Authorization="Bearer $($login.token)"}
Invoke-RestMethod "$base/auth/me" -Headers $headers
curl.exe -s -o NUL -w '%{http_code}' "$base/auth/me"
curl.exe -s -o NUL -w '%{http_code}' -H 'Authorization: Bearer invalid' "$base/auth/me"
```

Регистрация и `/me` с токеном — 200; оба отрицательных запроса — 401. Полный `$login` и `$headers` не выводить в материалы отчёта.

## CRUD через Gateway

Чтобы все операции попали в одно in-memory хранилище, на время демонстрации остановить второй экземпляр. Это отдельный сценарий; балансировка проверяется после его восстановления.

```powershell
docker stop catalog-2
try {
    $base = 'http://localhost:8080'
    $book = @{title='Test book'; author='Test author'; price=150; stock=3} | ConvertTo-Json
    $product = Invoke-RestMethod "$base/catalog/products" -Method Post -ContentType 'application/json' -Body $book
    $product
    $id = $product.id
    Invoke-RestMethod "$base/catalog/products"
    Invoke-RestMethod "$base/catalog/products/$id"
    Invoke-RestMethod "$base/catalog/products/$id" -Method Put -ContentType 'application/json' -Body '{"price":199,"stock":5}'
    Invoke-RestMethod "$base/catalog/products/$id" -Method Delete
    curl.exe -s -o NUL -w '%{http_code}' "$base/catalog/products/$id"
} finally {
    docker start catalog-2
}
docker compose up -d --wait
Start-Sleep -Seconds 6
```

POST — 201; GET/PUT/DELETE — 200; GET после удаления — 404. Список возвращает `instance_id` и `products`.

## Consul и балансировка

```powershell
Invoke-RestMethod 'http://localhost:8500/v1/agent/services' | ConvertTo-Json -Depth 5
(Invoke-RestMethod 'http://localhost:8500/v1/agent/checks').PSObject.Properties.Value | Select-Object ServiceID,Status
1..12 | ForEach-Object { (Invoke-RestMethod 'http://localhost:8080/catalog/products').instance_id }
```

Должны быть зарегистрированы `auth`, `catalog-1`, `catalog-2`, статусы — `passing`. В последовательности ответов должны присутствовать оба Catalog. Посторонние запросы из Swagger тоже участвуют в round-robin, поэтому могут изменить наблюдаемый порядок.

## Отказ и восстановление

```powershell
docker stop catalog-1
try {
    1..12 | ForEach-Object { (Invoke-RestMethod 'http://localhost:8080/catalog/products').instance_id }
    Invoke-RestMethod 'http://localhost:8500/v1/agent/services' | ConvertTo-Json -Depth 5
} finally {
    docker start catalog-1
}
docker compose up -d --wait
Start-Sleep -Seconds 6
1..12 | ForEach-Object { (Invoke-RestMethod 'http://localhost:8080/catalog/products').instance_id }
```

После остановки ответы должны приходить от `catalog-2` без HTTP-ошибок; `catalog-1` должен исчезнуть из реестра Consul при штатной остановке. После запуска и окончания `fail_timeout` оба экземпляра снова участвуют в балансировке.

## Автоматические интеграционные проверки

Требуется Python 3.12+ на хосте, сторонних пакетов для тестового скрипта не нужно. Для текущего локального окружения:

```powershell
.\.venv\Scripts\python.exe tests/integration.py
```

На другом компьютере с Python:

```powershell
python tests/integration.py
```

Тест проверяет Docker healthchecks и закрытые API-порты, совпадение образов Catalog, Consul и HTTP UI, Swagger, JWT (включая подпись), отрицательные сценарии, Passlib, CRUD на каждом экземпляре через Gateway, балансировку, остановку и восстановление, запуск приложения раньше Consul. Он временно останавливает контейнеры лабораторной и восстанавливает их в `finally`. Запускать без параллельных демонстраций. Результат: `evidence/integration-results.json`, поле `passed` последнего события должно быть `true`.

## Остановка и диагностика

```powershell
docker compose logs --tail 100 auth catalog-1 catalog-2 nginx consul
docker compose exec -T nginx nginx -t
docker compose down
```

Остановка системы уничтожает данные в памяти. Для повторного запуска: `docker compose up --build -d`.

## Источники

- [FastAPI lifespan](https://fastapi.tiangolo.com/advanced/events/)
- [Consul Agent Service API](https://developer.hashicorp.com/consul/api-docs/agent/service)
- [Nginx proxy_next_upstream](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_next_upstream)
- [Passlib PBKDF2](https://passlib.readthedocs.io/en/stable/lib/passlib.hash.pbkdf2_digest.html)
- Фактические результаты этой реализации — в `evidence/`; сценарий защиты — `DEFENSE_GUIDE.md`.
