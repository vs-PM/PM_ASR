# PM_ASR — сервис протоколирования встреч

PM_ASR превращает аудиозаписи митингов в структурированные протоколы: сервис режет звуковой поток на интервалы, распознаёт речь, строит эмбеддинги, генерирует суммаризацию и ведёт аудит выполнения задач с помощью FastAPI-бэкенда и Next.js‑интерфейса.【F:backend/app/services/jobs/workflow.py†L29-L63】【F:frontend/src/app/layout.tsx†L10-L21】

## Содержание
- [Ключевые возможности](#ключевые-возможности)
- [Архитектура и основные модули](#архитектура-и-основные-модули)
- [Требования](#требования)
- [Конфигурация (.env)](#конфигурация-env)
- [Подготовка базы данных](#подготовка-базы-данных)
- [Запуск backend](#запуск-backend)
- [Сценарий использования API](#сценарий-использования-api)
- [Frontend](#frontend)
- [Утилиты и инструменты](#утилиты-и-инструменты)

## Ключевые возможности
- Полный ML‑конвейер: сегментация по диаризации, VAD или фиксированным окнам → распознавание Whisper → генерация эмбеддингов → многошаговая суммаризация в фоне.【F:backend/app/services/jobs/workflow.py†L29-L63】【F:backend/app/services/pipeline/vad.py†L107-L175】【F:backend/app/services/summary/service.py†L67-L199】
- Автоматическая нормализация аудио через FFmpeg и Whisper `large-v3` с поддержкой CUDA/CPU, что позволяет принимать разные форматы входных файлов.【F:backend/app/services/pipeline/media.py†L12-L91】【F:backend/app/services/pipeline/asr.py†L15-L111】
- Хранение данных в PostgreSQL с расширением `pgvector`: транскрипты, сегменты, диаризация, эмбеддинги, суммаризации, задачи, аудит и файлы пользователей.【F:backend/app/db/models.py†L13-L200】
- Прозрачный мониторинг исполнения: статусы и прогресс пишутся в `mfg_job`/`mfg_job_event`, есть WebSocket‑канал для live‑обновлений и REST‑эндпоинт аудита для администраторов.【F:backend/app/services/jobs/progress.py†L12-L108】【F:backend/app/api/v1/ws.py†L40-L109】【F:backend/app/api/v1/admin.py†L11-L39】
- Health‑checks проверяют доступность БД, Ollama, FFmpeg и GPU, а UI содержит отдельную страницу мониторинга инфраструктуры.【F:backend/app/api/v1/health.py†L20-L100】【F:frontend/src/app/ping/page.tsx†L37-L195】
- Cookie‑based аутентификация с Argon2, ротацией refresh‑токенов и доступом к защищённым маршрутам из middleware Next.js.【F:backend/app/api/v1/auth.py†L26-L107】【F:frontend/middleware.ts†L4-L56】
- Next.js 15 UI с авторизацией, загрузкой аудио, созданием митингов, контролем очереди задач и health‑дашбордом; состояние данных синхронизируется через React Query.【F:frontend/src/app/login/LoginForm.tsx†L22-L107】【F:frontend/src/components/CreateMeeting.tsx†L19-L308】【F:frontend/src/app/audio/page.tsx†L17-L70】【F:frontend/src/app/meetings/page.tsx†L18-L87】【F:frontend/src/app/jobs/page.tsx†L16-L69】

## Архитектура и основные модули
### Backend (FastAPI)
- Приложение собирается в `backend/main.py`: подключены роутеры для загрузки файлов, запуска пайплайна, суммаризации, протокола «в один клик», health‑проверок, аутентификации, административного аудита и WebSocket‑ов.【F:backend/main.py†L17-L50】
- Исключения валидируются централизованно, а логирование настраивается через собственную фабрику с переключением dev/prod режимов.【F:backend/app/core/errors.py†L1-L12】【F:backend/app/core/logger.py†L1-L58】

### Пайплайн обработки
- Вызовы `process_*` собираются в `app/services/jobs/api.py`, который прокидывает контекст в движок workflow.【F:backend/app/services/jobs/api.py†L1-L34】
- Workflow получает advisory‑lock на транскрипт и по шагам выполняет сегментацию, ASR, эмбеддинги и суммаризацию, гарантируя очистку ресурсов и перевод статусов.【F:backend/app/services/jobs/workflow.py†L23-L71】
- Диаризация выполняется через `pyannote` с ленивой инициализацией и обязательным Hugging Face токеном; альтернативные режимы VAD/fixed режут аудио без идентификации спикеров.【F:backend/app/services/pipeline/diarization.py†L22-L114】【F:backend/app/services/pipeline/vad.py†L107-L175】
- Конвертация аудио и разрезка окон выполняется на лету: `compose.py` фильтрует существующие сегменты, вызывает ASR для каждого окна и делает UPSERT в БД.【F:backend/app/services/pipeline/compose.py†L21-L215】
- Эмбеддинги текстов получают через Ollama `/api/embed`, а суммаризация использует многошаговый RAG с выборкой похожих сегментов и финальным генератором (например, LLaMA).【F:backend/app/services/pipeline/embeddings.py†L9-L31】【F:backend/app/services/summary/service.py†L67-L199】

### Хранилище данных
- SQLAlchemy‑модели описывают весь домен: транскрипты, сегменты, диаризацию, эмбеддинги (768‑мерный вектор), резюме, действия, статус задач, спикеров, пользователей, refresh‑токены, файлы и журнал аудита.【F:backend/app/db/models.py†L13-L200】
- Alembic‑миграции лежат в `app/db/migrations`, запуск `alembic` использует конфигурацию `alembic.ini`. Первые миграции создают нужные таблицы и обновляют размерность `pgvector`.【F:backend/alembic.ini†L1-L6】【F:backend/app/db/migrations/versions/9f62774fdcaa_initial_tables.py†L1-L45】

### Очередь задач и наблюдаемость
- Статус и прогресс сохраняются в `mfg_job`, события — в `mfg_job_event`, а `pg_advisory_lock` защищает от параллельных запусков на одном транскрипте.【F:backend/app/services/jobs/progress.py†L12-L108】【F:backend/app/services/jobs/locks.py†L13-L38】
- WebSocket `/ws/jobs/{id}` отдаёт текущий статус и «тянет» новые записи раз в секунду.【F:backend/app/api/v1/ws.py†L40-L109】
- Аудит действий (`login`, `upload`, `start_step` и т.д.) пишется в `mfg_audit_log` и доступен админам через `GET /api/v1/admin/audit`.【F:backend/app/services/audit.py†L1-L21】【F:backend/app/api/v1/admin.py†L11-L39】
- Health‑роуты `/healthz`, `/readyz`, `/livez` проверяют БД, Ollama, FFmpeg и CUDA, возвращая структурированную телеметрию для UI.【F:backend/app/api/v1/health.py†L20-L100】

### Интерфейсы и UI
- Базовый layout включает SSR‑шапку с проверкой сессии, глобальные провайдеры React Query и адаптивную верстку.【F:frontend/src/app/layout.tsx†L10-L21】【F:frontend/src/components/site/HeaderServer.tsx†L1-L35】【F:frontend/src/app/providers.tsx†L1-L24】
- Публичная посадочная страница рассказывает о преимуществах сервиса, а после логина пользователь попадает на дашборд с основными разделами.【F:frontend/src/components/Landing.tsx†L3-L44】【F:frontend/src/app/page.tsx†L5-L39】
- UI реализует формы входа, загрузки аудио/выбора существующих файлов, списки митингов и задач, страницу детализации митинга с быстрым запуском пайплайна, а также health‑дашборд с карточками проверок.【F:frontend/src/app/login/LoginForm.tsx†L22-L107】【F:frontend/src/components/CreateMeeting.tsx†L19-L308】【F:frontend/src/app/audio/page.tsx†L17-L70】【F:frontend/src/app/meetings/[id]/page.tsx†L19-L93】【F:frontend/src/app/jobs/page.tsx†L16-L69】【F:frontend/src/app/ping/page.tsx†L37-L195】

## Требования
### Backend
- Python 3.10+, pip, FFmpeg и libsndfile (для конвертации аудио и загрузки моделей) — см. установку в Dockerfile.【F:Dockerfile†L7-L13】
- GPU с CUDA 12.3.2 (опционально) — Whisper автоматически переключится на CPU, но для ускорения стоит настроить `DEVICE=cuda`.【F:backend/app/services/pipeline/asr.py†L15-L25】【F:backend/app/core/config.py†L7-L10】
- Hugging Face токен (`HF_TOKEN`) обязателен для загрузки `pyannote/speaker-diarization-3.1`.【F:backend/app/core/config.py†L7-L13】【F:backend/app/services/pipeline/diarization.py†L22-L38】
- Запущенный Ollama с моделями суммаризации и эмбеддингов, доступный по HTTP (`OLLAMA_URL`).【F:backend/app/core/config.py†L11-L33】【F:backend/app/services/summary/service.py†L67-L191】
- PostgreSQL 14+ с расширением `pgvector` (для таблицы `mfg_embedding`).【F:backend/app/db/models.py†L31-L58】
- Каталог для загруженных файлов (`UPLOAD_DIR`, по умолчанию `/data/uploads`) доступен на запись; структура по месяцам создаётся автоматически при загрузке файлов.【F:backend/app/core/config.py†L80-L97】【F:backend/app/api/v1/files.py†L21-L57】

### Frontend
- Node.js 20+ и pnpm/npm/yarn; проект использует Next.js 15.5.2, React 19 и Turbopack скрипты `dev`, `build`, `start`, `lint`.【F:frontend/package.json†L5-L36】
- Переменная `AUTH_API_BASE` (и при необходимости `NEXT_PUBLIC_API_BASE`) указывает на адрес бекенда для серверных и клиентских запросов.【F:frontend/middleware.ts†L4-L56】【F:frontend/src/components/CreateMeeting.tsx†L8-L47】【F:frontend/src/components/site/LogoutClient.tsx†L4-L21】

## Конфигурация (.env)
Backend читает настройки из файла `.env` в каталоге `backend` (см. `Settings.model_config`).【F:backend/app/core/config.py†L82-L97】 Минимальный пример:

```env
# ML и внешние сервисы
HF_TOKEN=hf_xxxxxxxxxxxxxxxxx
DEVICE=cuda
OLLAMA_URL=http://localhost:11434
EMBEDDING_MODEL=nomic-embed-text
SUMMARIZE_MODEL=llama3.1:8b-instruct
OLLAMA_CHAT_TIMEOUT=600
OLLAMA_CONNECT_TIMEOUT=10
OLLAMA_READ_TIMEOUT=0
OLLAMA_WRITE_TIMEOUT=0
OLLAMA_KEEP_ALIVE=30m
SUMMARIZE_NUM_CTX=8192
SUMMARIZE_TEMPERATURE=0.2
SUMMARIZE_TOP_P=0.9
SUMMARIZE_NUM_PREDICT_BATCH=256
SUMMARIZE_NUM_PREDICT_FINAL=512
MAX_REFS_CHARS=3000
MAX_DRAFT_CHARS=8000
MAX_FINAL_DRAFT_CHARS=12000
RAG_CHUNK_CHAR_LIMIT=3000
RAG_TOP_K=6
RAG_MIN_SCORE=0.35

# Сегментация и FFmpeg
VAD_AGGRESSIVENESS=2
VAD_FRAME_MS=20
VAD_MIN_SPEECH_MS=250
VAD_MIN_SILENCE_MS=300
VAD_MERGE_MAX_GAP_SEC=0.3
VAD_MAX_SEGMENT_SEC=30
SEG_OVERLAP_SEC=2.0
FIXED_WINDOW_SEC=30
FIXED_OVERLAP_SEC=5
FFMPEG_THREADS=0
FFMPEG_FILTER_THREADS=0
FFMPEG_PROBESIZE=1M
FFMPEG_ANALYZEDURATION=0
FFMPEG_USE_SOXR=false

# База данных
OLLAMA_DB_HOST=localhost
OLLAMA_DB_PORT=5432
OLLAMA_DB_NAME=pm_asr
OLLAMA_DB_USER=pm_asr
OLLAMA_DB_PASSWORD=pm_asr

# Логирование и безопасность
OLLAM_PROD=false
OLLAMA_LOG_PATH=./logs/app.log
JWT_SECRET=dev_secret
JWT_ALGO=HS256
ACCESS_TTL_MINUTES=15
REFRESH_TTL_DAYS=14
COOKIE_DOMAIN=localhost
COOKIE_SECURE=false
UPLOAD_DIR=/data/uploads
```

## Подготовка базы данных
1. Создайте БД и включите расширение `vector` (один раз на схему): `CREATE EXTENSION IF NOT EXISTS vector;` — это необходимо для хранения эмбеддингов.【F:backend/app/db/models.py†L54-L58】
2. Выполните миграции Alembic: `alembic -c backend/alembic.ini upgrade head`. Конфигурация уже указывает на папку `app/db/migrations` с актуальными скриптами.【F:backend/alembic.ini†L1-L6】【F:backend/app/db/migrations/versions/9f62774fdcaa_initial_tables.py†L1-L45】

## Запуск backend
1. Создайте виртуальное окружение и установите зависимости:
   ```bash
   cd backend
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
   【F:backend/requirements.txt†L1-L47】
2. Убедитесь, что `.env` заполнен и миграции применены (см. выше).
3. Запустите приложение:
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 7000 --reload
   ```
   【F:backend/main.py†L66-L67】
4. Создайте административного пользователя при первом запуске:
   ```bash
   python -m tools.create_admin
   ```
   Скрипт запросит логин и пароль, захэширует их Argon2 и запишет пользователя в БД.【F:backend/tools/create_admin.py†L1-L18】
5. Проверка состояния сервиса доступна по `GET /api/v1/healthz`, `GET /api/v1/readyz` и `GET /api/v1/livez`. Эти эндпоинты используются и в web‑интерфейсе страницы `/ping`.【F:backend/app/api/v1/health.py†L65-L100】【F:frontend/src/app/ping/page.tsx†L37-L195】

## Сценарий использования API
1. **Аутентификация.** Отправьте `POST /api/v1/auth/login` с JSON `{ "username": "...", "password": "..." }`; ответ выставит `access_token` и `refresh_token` в HTTP‑куки.【F:backend/app/api/v1/auth.py†L45-L59】
2. **Загрузка аудио.** Передайте файл через `POST /api/v1/files` (`multipart/form-data`) — сервис сохранит его в `UPLOAD_DIR` и вернёт `id`, размер и MIME‑тип.【F:backend/app/api/v1/files.py†L21-L57】
3. **Создание транскрипта.** Вызов `POST /api/v1/transcripts` с телом `{ "title": "Sprint review", "meeting_id": 123, "file_id": <ID> }` создаст запись и асинхронно запустит пайплайн обработки.【F:backend/app/api/v1/transcripts.py†L118-L151】
4. **Запуск отдельных шагов (опционально).** Можно вручную дёргать `POST /pipeline/{id}`, `POST /embeddings/{id}` или `POST /summary/{id}?lang=ru&format=text` для повторного запуска конкретных стадий.【F:backend/app/api/v1/pipeline.py†L15-L35】【F:backend/app/api/v1/embeddings.py†L15-L35】【F:backend/app/api/v1/summary.py†L19-L87】
5. **Полный протокол из файла.** `POST /protokol` принимает файл, `meeting_id` и режим сегментации (`diarize|vad|fixed`) и запускает связанный workflow (диаризация/ASR/эмбеддинги/суммаризация).【F:backend/app/api/v1/protokol.py†L16-L73】
6. **Получение результатов.**
   - `GET /api/v1/transcripts/{id}` — текущий статус, исходный и обработанный текст.【F:backend/app/api/v1/transcripts.py†L100-L112】
   - `GET /summary/{id}` — статус и финальный текст суммаризации.【F:backend/app/api/v1/summary.py†L62-L87】
   - `GET /api/v1/files` — список загруженных файлов текущего пользователя.【F:backend/app/api/v1/files.py†L59-L93】
7. **Мониторинг прогресса.** Подключитесь к WebSocket `/ws/jobs/{transcript_id}` (передав `?token=` или используя cookie) для получения событий прогресса и статусов в реальном времени.【F:backend/app/api/v1/ws.py†L40-L109】
8. **Аудит.** Администраторы могут просматривать действия пользователей через `GET /api/v1/admin/audit` с пагинацией и фильтрами по пользователю/типу события.【F:backend/app/api/v1/admin.py†L11-L39】

> 💡 Для быстрой проверки пайплайна без UI используйте `python scripts/smoke_jobs.py --file path/to/audio.m4a --seg-mode diarize`, который создаёт транскрипт, запускает workflow и печатает прогресс/итоговую сводку в консоль.【F:scripts/smoke_jobs.py†L1-L195】

## Frontend
1. Установите зависимости и запустите dev‑сервер:
   ```bash
   cd frontend
   pnpm install
   pnpm dev
   ```
   【F:frontend/package.json†L5-L9】
2. Создайте `.env.local` (или используйте переменные окружения) со ссылкой на бекенд:
   ```env
   AUTH_API_BASE=http://localhost:7000
   NEXT_PUBLIC_API_BASE=http://localhost:7000
   ```
   Эти параметры используются как на серверной стороне (middleware и SSR‑шапка), так и в клиентских запросах/Logout кнопке.【F:frontend/middleware.ts†L4-L56】【F:frontend/src/components/site/HeaderServer.tsx†L16-L35】【F:frontend/src/components/site/LogoutClient.tsx†L4-L21】
3. Основные разделы UI:
   - `/` — посадочная и после авторизации быстрый дашборд со ссылками на разделы.【F:frontend/src/app/page.tsx†L5-L39】
   - `/login` — форма входа с проверкой сессии и graceful‑редиректом на `next` маршрут.【F:frontend/src/app/login/LoginForm.tsx†L22-L107】【F:frontend/middleware.ts†L18-L52】
   - `/audio` — список загруженных файлов и кнопка обновления.【F:frontend/src/app/audio/page.tsx†L17-L70】
   - `/meetings`, `/meetings/new`, `/meetings/[id]` — создание митинга, просмотр статуса и быстрый запуск пайплайна по выбранным параметрам.【F:frontend/src/components/CreateMeeting.tsx†L19-L308】【F:frontend/src/app/meetings/page.tsx†L18-L87】【F:frontend/src/app/meetings/[id]/page.tsx†L19-L93】
   - `/jobs` — список фоновых задач с прогресс‑баром.【F:frontend/src/app/jobs/page.tsx†L16-L69】
   - `/ping` — health‑дашборд с карточками проверок, автообновлением и отображением RAW JSON ответа `/healthz`.【F:frontend/src/app/ping/page.tsx†L37-L195】

## Утилиты и инструменты
- **Smoke‑тест пайплайна:** `scripts/smoke_jobs.py` создаёт транскрипт, запускает `process_protokol`, ждёт завершения и печатает сводные метрики (число сегментов, эмбеддингов и т.д.). Отлично подходит для регрессионных проверок без UI.【F:scripts/smoke_jobs.py†L1-L195】
- **Создание администратора:** `python -m tools.create_admin` — интерактивное создание пользователя с ролью `admin`, пароль хэшируется через Argon2.【F:backend/tools/create_admin.py†L1-L18】
- **Docker:** базовый образ строится от `nvidia/cuda:12.3.2-cudnn9-runtime-ubuntu22.04`, устанавливает Python, FFmpeg и запускает `uvicorn main:app`. Перед сборкой убедитесь, что `backend/requirements.txt` скопирован в корень (Dockerfile ожидает `requirements.txt` рядом с Dockerfile) или поправьте инструкцию COPY.【F:Dockerfile†L1-L31】【F:backend/requirements.txt†L1-L47】
- **Логирование:** фабрика в `app/core/logger.py` создаёт отдельные обработчики для dev (stdout, DEBUG) и prod (файл, WARNING+). Путь к файлу берётся из `OLLAMA_LOG_PATH` конфигурации.【F:backend/app/core/logger.py†L1-L58】【F:backend/app/core/config.py†L66-L80】

Готово! После запуска бекенда и фронтенда вы получите полный цикл: загрузка аудио, прогон пайплайна, просмотр результатов, историю задач и мониторинг инфраструктуры.
