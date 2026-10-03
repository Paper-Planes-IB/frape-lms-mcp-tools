# Frappe LMS MCP — Paper Planes

Удалённый MCP для чтения Frappe LMS и Wiki через ClickUp Brain.
Основа: `anggun-indra/frape-lms-mcp-tools`, коммит `b8ece3fe8d1a18353c0b35c953e5afb6b19f56cb`.
Аудит: [AUDIT.md](AUDIT.md). Исходная документация сохранена в README.upstream.md как историческая.

## Подключение к ClickUp Brain

Рабочий URL: `https://lms.paper-planes.ru/mcp`.
Плановый отдельный адрес: `https://lms-mcp.paper-planes.ru/mcp`.
Для этого адреса нужна A-запись `lms-mcp` на IP сервера LMS.
Фактически проверенный адрес и результаты развёртывания фиксируются в DEPLOYMENT.md.

Администратор рабочего пространства добавляет пользовательский MCP-коннектор в настройках Brain,
указывает URL и заголовок `Authorization: Bearer <MCP_AUTH_TOKEN>`.
Токен получают из защищённого хранилища владельца сервера; в GitHub, переписку и комментарии его не помещают.
Если интерфейс поддерживает только OAuth, этот сервер с Bearer-токеном не будет совместим без дополнительной настройки коннектора.
Фактическое подключение внутри ClickUp выполняет администратор рабочего пространства.

Если коннектор принимает только URL, владелец сервера может установить `MCP_ALLOW_QUERY_TOKEN=1`
и добавить `?token=<MCP_AUTH_TOKEN>`. По умолчанию этот вариант отключён.
Не сохраняйте полные URL запросов в журналах прокси при его включении.

Доступно 14 инструментов:

- `list_courses`, `get_course`, `get_chapter`, `get_lesson`
- `list_quizzes`, `get_quiz`, `list_enrollments`, `list_batches`
- `list_cached_courses`, `get_cached_course`, `import_course_from_frappe`
- `list_kb_articles`, `get_kb_article`, `search_lms`

`import_course_from_frappe` сохраняет метаданные только в локальный SQLite-кеш.
Кеш разделён по адресу, сайту и API-учётной записи; секреты в него не записываются.
`get_course` и `get_chapter` возвращают идентификаторы дочерних разделов и уроков.
Уроки возвращаются как текст/Markdown. Вложенные ссылки не загружаются.
Поиск охватывает заголовки и содержимое; ограничение выдачи обозначается `truncated`.
В Wiki читаются опубликованные статьи. Для нескольких DocType используется ID `DocType::name`.
Категория для Wiki Document — идентификатор родительского документа.

## Установка

Python 3.11. Поддерживается FastMCP из MCP SDK 1.x; зависимость ограничена `mcp>=1.26,<2`.

```sh
pip install '.[dev]'
cp .env.example .env
chmod 600 .env
# Заполнить параметры и секреты, сгенерировать MCP_AUTH_TOKEN через secrets.token_urlsafe(48).
docker compose up -d --build
```

Docker запускается от UID 10001, корневая файловая система доступна только для чтения.
SQLite находится в отдельном volume. У MCP отсутствуют публичные порты; снаружи доступен HTTPS-прокси.
Для существующего Caddy используйте `docker compose -f deploy/compose-existing-proxy.yml up -d --build`:
сервис слушает только `127.0.0.1:8093`, добавьте соответствующий `reverse_proxy` в действующий прокси.
Порт 8080 и веб-панель исходного MCP не запускаются.

## Конфигурация

Полный пример — `.env.example`. Учётная запись Frappe использует API key/secret из окружения.
Вход по паролю и подключения из старой SQLite-базы не используются.
Перед созданием сервисного пользователя сделайте резервную копию БД и прав.
`deploy/provision_reader.py` создаёт отдельную роль с чтением восьми DocType, проверяет отсутствие
write/create/delete/share/submit и сохраняет credentials в закрытый файл внутри контейнера.
Повторный запуск при существующем пользователе останавливается без смены секретов.

`MCP_TRANSPORT` по умолчанию `stdio`; доступны `streamable-http` и `sse`.
SSE — альтернативный режим запуска по `/sse`, сообщения по `/messages/`; авторизация обязательна на обоих путях.
HTTP всегда требует `MCP_READ_ONLY=1` и токен минимум 32 байта.
`MCP_HOST`, `MCP_PORT`, `MCP_PATH` задают адрес, порт и путь HTTP.
В stdio можно явно включить старые инструменты записи через `MCP_READ_ONLY=0`; штатное значение — `1`.
Веб-панель отключена во всех режимах этого форка.

`KB_DOCTYPES` — список через запятую. Готовые схемы: Wiki Document, Wiki Page, Help Article.
Для своего DocType задайте JSON в `KB_FIELD_MAP` с полями `title`, `content`, `category`, `published`.
Пример: `{"Custom Article":{"title":"title","content":"body","category":"category","published":"published"}}`.

`GET /health` публичен и проверяет работоспособность процесса, без проверки доступа к Frappe.
Остальные HTTP-пути без корректного токена возвращают 401.
Журнал в stdout содержит метод и код ответа; URL, параметры, тела и токены исключены.

## Проверка

```sh
python -m pytest tests -q
npx @modelcontextprotocol/inspector
```

В Inspector выберите Streamable HTTP, укажите URL и Bearer-токен.
Проверьте `tools/list`, `list_courses`, чтение урока и статьи, поиск по содержимому.
Без токена ожидается 401; вызовы `create_course` и `delete_course` дают Unknown tool.
Для командной проверки: `python deploy/smoke.py URL` с `MCP_AUTH_TOKEN` в окружении.
Скрипт выводит только результаты проверок, без токенов и учебного контента.

## Откат

Остановить отдельный compose-сервис MCP и убрать только его маршрут из Caddy.
Отключить сервисного пользователя Frappe и отозвать его API-секрет.
Старые роли и права сохраняются в резервном снимке. Не восстанавливать всю БД ради отключения коннектора.
