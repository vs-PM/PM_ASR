import os
import torch
from pathlib import Path
from typing import List, Dict, Any

from app.services.asr_service import transcribe_with_diarization
from app.logger import get_logger
from app.database import get_pool

log = get_logger(__name__)


async def process_and_save(audio_path: str, record_id: int) -> None:
    """
    Фоновая задача, которая:

    1. Получает диаризованные сегменты (с транскрипцией и embedding);
    2. Сохраняет их в две таблицы:
       * `mfg_segment`  – только текст и метаданные;
       * `mfg_embedding` – embedding (vector) и FK на segment.
    3. Обновляет статус транскрипции в `mfg_transcript`.
    4. Очищает временные файлы и CUDA‑кеш.

    Параметры:
        audio_path (str): абсолютный путь к загруженному файлу.
        record_id (int): id записи в `mfg_transcript`.
    """

    log.info(f"Запуск фоновой обработки для {record_id} ({audio_path})")
    pool = await get_pool()

    try:
        # -----------------------------------------------------------------
        # 1️⃣ Диаризация + транскрипция + embedding
        # -----------------------------------------------------------------
        segments: List[Dict[str, Any]] = await transcribe_with_diarization(audio_path)
        log.debug(f"Получено {len(segments)} сегментов для записи {record_id}")

        async with pool.acquire() as conn:
            # 2️⃣ Обновляем статус до «done» – будем менять позже, если что‑то
            #    пройдёт не так, будем выставлять «error».
            await conn.execute(
                "UPDATE mfg_transcript SET status = 'done' WHERE id = $1",
                record_id,
            )

            # 3️⃣ Вставляем сегменты (без embedding)
            #    Получаем обратно их id, чтобы позже вставить embeddings.
            segment_ids = await conn.fetch(
                """
                INSERT INTO mfg_segment
                    (transcript_id, speaker, start_ts, end_ts, text)
                VALUES
                    ($1, $2, $3, $4, $5)
                RETURNING id
                """,
                *((
                    record_id,
                    seg["speaker"],
                    seg["start_ts"],
                    seg["end_ts"],
                    seg["text"],
                )
                for seg in segments),
            )

            # 4️⃣ Заполняем в segments FK на сегмент
            for seg, seg_id in zip(segments, segment_ids):
                seg["segment_id"] = seg_id["id"]  # `fetch` возвращает tuple (dict)

            # 5️⃣ Вставляем embeddings (только если они не `None`)
            embeddings_to_insert = [
                (
                    seg["segment_id"],
                    seg["embedding"],
                )
                for seg in segments
                if seg["embedding"] is not None
            ]

            if embeddings_to_insert:
                await conn.executemany(
                    """
                    INSERT INTO mfg_embedding
                        (segment_id, embedding)
                    VALUES
                        ($1, $2)
                    """,
                    embeddings_to_insert,
                )
            else:
                log.warning(
                    f"Для записи {record_id} embedding‑таблица осталась пустой"
                )

        # -----------------------------------------------------------------
        # 4️⃣ Финальный статус и чистка
        # -----------------------------------------------------------------
        await conn.execute(
            "UPDATE mfg_transcript SET status = 'done' WHERE id = $1",
            record_id,
        )
        log.info(f"Данные успешно сохранены для {record_id}")

    except Exception as exc:
        # Если что‑то пошло не так, обновляем статус до «error»
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE mfg_transcript SET status = 'error' WHERE id = $1",
                record_id,
            )
        log.exception(f"Ошибка при обработке записи {record_id}")
        raise

    finally:
        # -----------------------------------------------------------------
        # 5️⃣ Очистка временных файлов и CUDA‑кеш
        # -----------------------------------------------------------------
        try:
            # Удаляем сам исходный файл – это делается в `background` в основной
            # pipeline, но иногда файл может остаться, поэтому проверяем.
            if Path(audio_path).exists():
                Path(audio_path).unlink()
                log.debug(f"Удалён временный файл {audio_path}")
        except OSError as e:
            log.warning(f"Не удалось удалить файл {audio_path}: {e}")

        # Освобождаем GPU‑память, если работаем на CUDA
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            log.debug("CUDA‑кеш очищен")

        log.info(f"Фоновая обработка завершена для записи {record_id}")