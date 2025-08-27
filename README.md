
# Speech‑to‑Text API с диаризацией и эмбеддингом

> **FastAPI** + **faster‑whisper** + **pyannote** + **Ollama**  
> REST‑интерфейс для асинхронной транскрипции аудио с выделением говорящих и генерацией эмбеддингов.

---

## 1. 📌 Описание проекта

Веб‑сервис, который:

1. Принимает аудиофайл (`multipart/form-data`).
2. Делит его по участникам разговора (диаризация).
3. Транскрибирует каждый сегмент с помощью модели `medium` от Whisper.
4. Генерирует вектор‑представление текста через Ollama.
5. Сохраняет результат в PostgreSQL (таблицы `transcripts` и `segments`).
6. Делает всю тяжёлую работу в фоне, чтобы клиент сразу получил ID задачи.

**Плюсы**

- Полностью асинхронная реализация (`asyncio` + `asyncpg`).
- Параллельное использование GPU (Whisper) и CPU (diarization, embeddings).
- Логирование уровня `DEBUG`/`INFO`/`ERROR` по модулям – легко отлавливать ошибки.
- Docker‑образ готов к деплою на любой инфраструктуре.

---

## 2. 🚀 Быстрый старт

> **Требования**: Docker 24+, Docker‑Compose, `make` (опционально).

### 2.1. Клонируйте репозиторий

```bash
git clone https://github.com/vs-PM/PM_ASR.git
cd speech-to-text
```

### 2.2. Переменные окружения

Создайте файл `.env` в корне проекта (см. `.env.example`):

```dotenv
# PostgreSQL
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=stt
POSTGRES_USER=stt
POSTGRES_PASSWORD=stt

# HuggingFace
HF_TOKEN=hf_XXXXXXXXXXXXXXXXXXXX

# Ollama
OLLAMA_URL=http://ollama:11434
MODEL_NAME_EMBEDDED=sentence-transformers/all-MiniLM-L6-v2

# Logging
LOG_LEVEL=DEBUG
```

### 2.3. Запуск Docker

```bash
make docker-build
make docker-up
```

После того как контейнеры запустятся, сервис будет доступен по `http://localhost:8000`.

> **Важно** – укажите `HF_TOKEN`, иначе `pyannote` не загрузит модель.  
> Если хотите использовать локальный Whisper без GPU, настройте `DEVICE=cpu` в `asr_service.py`.

---

## 3. 📄 API

### 3.1. POST `/recognize`

> **Описание** – Загружает аудиофайл, возвращает `id` транскрипции и статус `processing`.

| Поле | Тип | Описание |
|------|-----|----------|
| `file` | `multipart/form-data` | Аудио‑файл (wav, mp3, m4a) |
| `response` | `RecognizeResponse` | `{ "status": "processing", "id": 42, "filename": "audio.mp3" }` |

**Пример запроса**:

```bash
curl -X POST "http://localhost:8000/recognize" \
     -F "file=@/path/to/audio.mp3"
```

### 3.2. GET `/status/{record_id}`

> **Описание** – Возвращает статус и, если завершена, список сегментов.

| Поле | Тип | Описание |
|------|-----|----------|
| `status` | `string` | `processing`, `done`, `error` |
| `segments` | `list[Segment]` | При `done`. |

**Пример запроса**:

```bash
curl http://localhost:8000/status/42
```

#### Ответ (пример):

```json
{
  "status": "done",
  "segments": [
    {
      "speaker": "spk_0",
      "start_ts": 0.0,
      "end_ts": 12.4,
      "text": "Привет, как дела?"
    },
    {
      "speaker": "spk_1",
      "start_ts": 12.5,
      "end_ts": 24.7,
      "text": "Все отлично, спасибо."
    }
  ]
}
```

---

## 4. 🧩 Структура проекта

```
speech-to-text/
├─ app/
│  ├─ __init__.py
│  ├─ config.py          # pydantic settings + DSN
│  ├─ logger.py          # get_logger
│  ├─ router.py          # FastAPI router (recognize, status)
│  ├─ services/
│  │  ├─ asr_service.py # Whisper + diarization pipeline
│  │  ├─ diarization.py # pyannote
│  │  ├─ embeddings.py  # Ollama запросы
│  │  └─ background.py  # background task + cleanup
│  ├─ database.py        # asyncpg pool + helpers
│  ├─ models.py          # Pydantic schemas
│  └─ main.py            # FastAPI приложение
├─ Dockerfile
├─ .env.example
├─ requirements.txt
└─ README.md
```

---

## 5. 🛠️ Логирование

- Логи выводятся в консоль и/или файл (если настроено `FileHandler` в `logger.py`).
- Уровень логов определяется переменной `LOG_LEVEL` (`DEBUG`, `INFO`, `WARNING`, `ERROR`).
- В каждом модуле используется `log = get_logger(__name__)`.

Пример лог‑строки:

```
2025-08-26 15:02:10 | INFO     | app.services.asr_service:61 | Running diarization
2025-08-26 15:02:12 | DEBUG    | app.services.asr_service:102 | Whisper generated 12 sub‑segments
```

---

## 6. 🧪 Тестирование

> Тесты пока отсутствуют, но их добавление возможно через `pytest` и `httpx.AsyncClient`.

```bash
pytest
```

---

## 7. 🔄 Валидация схем

В `app/models.py` находятся схемы:

```python
class RecognizeResponse(BaseModel):
    status: str
    id: int
    filename: str

class Segment(BaseModel):
    speaker: str
    start_ts: float
    end_ts: float
    text: str
```

FastAPI автоматически генерирует OpenAPI‑документацию по `http://localhost:8000/docs`.

---

## 7. 📚 Документация по настройке

- **Whisper** – `asr_service.py` использует `DEVICE=...`.  
  Для CPU‑модели замените `DEVICE = "cpu"` и установите `torch.no_grad()` при необходимости.

- **pyannote** – модель `pyannote/speaker-diarization` скачивается через HuggingFace.  
  Требует токен `HF_TOKEN`. Можно заменить модель через `MODEL_NAME` в конфиге.

- **Ollama** – доступ через HTTP API. Убедитесь, что сервис Ollama уже запущен.  
   `http://localhost:11434`.

- **PostgreSQL** – создайте схему вручную или подключите миграции с `alembic`.  
  Минимальный скрипт:

```sql
CREATE TABLE transcripts (
  id SERIAL PRIMARY KEY,
  filename TEXT NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

CREATE TABLE segments (
  id SERIAL PRIMARY KEY,
  transcript_id INT REFERENCES transcripts(id),
  speaker TEXT,
  start_ts DOUBLE PRECISION,
  end_ts DOUBLE PRECISION,
  text TEXT,
  embedding TEXT
);
```

---

## 7. 📈 Мониторинг и деплой

- В продакшн‑окружении можно подключить **Prometheus** через `prometheus_fastapi_instrumentator`.
- Для лог‑агрегации – `graylog`, `ELK`, `Fluentd` (в зависимости от вашей инфраструктуры).
- `Docker‑Compose` уже содержит сервисы: `app`, `postgres`, `ollama`, `huggingface-hub` (по желанию) – легко развернуть в кластере.

---

## 8. 🤝 Содействие проекту

1. Создайте `issue` с описанием задачи/ошибки.  
2. Fork репозитория и сделайте пул‑реквест.  
3. Убедитесь, что все тесты проходят (`make test`).
4. Логика, которая меняется, должна быть покрыта комментариями и логами.  
5. Если добавляете новую модель/интеграцию – обновите `README` и `requirements.txt`.

---

## 9. 📜 Лицензия

MIT License – свободно используйте, модифицируйте и делитесь.

---

## 10. 🔗 Ссылки

- **GitHub**: https://github.com/vs-PM/PM_ASR.git
- **OpenAPI Docs**: http://localhost:8000/docs (после запуска)  
- **HuggingFace**: https://huggingface.co/  

---