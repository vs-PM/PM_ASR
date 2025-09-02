import torch
from pathlib import Path
from app.services.asr_service import transcribe_file
from app.services.diarization_service import diarize_file
from app.services.embeddings_service import embed_text
from app.services.pipeline_service import process_pipeline_segments
from app.services.summary_service import generate_protocol
from app.database import async_session
from app.models import MfgTranscript, MfgDiarization, MfgSegment, MfgEmbedding
from app.logger import get_logger

log = get_logger(__name__)

# ----------------------------
# 1️⃣ Транскрипция целого файла
# ----------------------------
async def process_transcription(transcript_id: int, audio_path: str):
    log.info(f"Запуск фоновой транскрипции для transcript_id={transcript_id}, путь к файлу={audio_path}")
    async with async_session() as session:
        transcript = await session.get(MfgTranscript, transcript_id)
        if not transcript:
            log.error(f"Запись транскрипта transcript_id={transcript_id} не найдена в БД")
            return

        try:
            log.debug(f"Вызываем функцию транскрипции файла: {audio_path}")
            text = await transcribe_file(audio_path)
            transcript.processed_text = text
            transcript.status = "transcription_done"
            session.add(transcript)
            await session.commit()
            log.info(f"Транскрипция завершена для transcript_id={transcript_id}, длина текста={len(text)}")
        except Exception:
            transcript.status = "error"
            session.add(transcript)
            await session.commit()
            log.exception(f"Ошибка при транскрипции файла для transcript_id={transcript_id}")
        finally:
            try:
                Path(audio_path).unlink(missing_ok=True)
                log.debug(f"Временный аудиофайл {audio_path} удалён")
            except Exception:
                log.warning(f"Не удалось удалить временный аудиофайл {audio_path}")
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                log.debug("Очистка кэша CUDA после транскрипции")
            log.info(f"Фоновая задача транскрипции завершена для transcript_id={transcript_id}")

# ----------------------------
# 2️⃣ Диаризация
# ----------------------------
async def process_diarization(transcript_id: int, audio_path: str):
    log.info(f"Запуск фоновой диаризации для transcript_id={transcript_id}, файл={audio_path}")
    async with async_session() as session:
        transcript = await session.get(MfgTranscript, transcript_id)
        if not transcript:
            log.error(f"Запись транскрипта transcript_id={transcript_id} не найдена в БД")
            return

        try:
            log.debug(f"Вызываем функцию диаризации файла: {audio_path}")
            chunks = await diarize_file(audio_path)
            for chunk in chunks:
                session.add(MfgDiarization(
                    transcript_id=transcript_id,
                    speaker=chunk["speaker"],
                    start_ts=chunk["start_ts"],
                    end_ts=chunk["end_ts"],
                    file_path=chunk["file_path"]
                ))
            transcript.status = "diarization_done"
            session.add(transcript)
            await session.commit()
            log.info(f"Диаризация завершена для transcript_id={transcript_id}, количество чанков={len(chunks)}")
        except Exception as e:
            transcript.status = "error"
            session.add(transcript)
            await session.commit()
            log.exception(f"Ошибка при диаризации для transcript_id={transcript_id}")
        finally:
            try:
                Path(audio_path).unlink(missing_ok=True)
                log.debug(f"Временный аудиофайл {audio_path} удалён после диаризации")
            except Exception:
                log.warning(f"Не удалось удалить временный аудиофайл {audio_path}")
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                log.debug("Очистка кэша CUDA после диаризации")
            log.info(f"Фоновая задача диаризации завершена для transcript_id={transcript_id}")


# ----------------------------
# 3️⃣ Pipeline: транскрипция чанков
# ----------------------------
async def process_pipeline(transcript_id: int):
    log.info(f"Запуск pipeline для transcript_id={transcript_id}")
    try:
        await process_pipeline_segments(transcript_id)
        log.info(f"Pipeline успешно завершен для transcript_id={transcript_id}")
    except Exception as e:
        async with async_session() as session:
            transcript = await session.get(MfgTranscript, transcript_id)
            if transcript:
                transcript.status = "error"
                session.add(transcript)
                await session.commit()
        log.exception(f"Ошибка при выполнении pipeline для transcript_id={transcript_id}")


# ----------------------------
# 4️⃣ Генерация эмбеддингов
# ----------------------------
async def process_embeddings(transcript_id: int):
    log.info(f"Запуск генерации эмбеддингов для transcript_id={transcript_id}")
    async with async_session() as session:
        transcript = await session.get(MfgTranscript, transcript_id)
        if not transcript:
            log.error(f"Запись транскрипта transcript_id={transcript_id} не найдена в БД")
            return

        try:
            segments_res = await session.execute(
                MfgSegment.__table__.select().where(MfgSegment.transcript_id == transcript_id)
            )
            segments = segments_res.fetchall()
            log.info(f"Найдено сегментов для эмбеддингов: {len(segments)}")

            for seg in segments:
                emb = await embed_text(seg.text)
                if emb:
                    session.add(MfgEmbedding(segment_id=seg.id, embedding=emb))
            transcript.status = "embeddings_done"
            session.add(transcript)
            await session.commit()
            log.info(f"Генерация эмбеддингов завершена для transcript_id={transcript_id}")
        except Exception as e:
            transcript.status = "error"
            session.add(transcript)
            await session.commit()
            log.exception(f"Ошибка при генерации эмбеддингов для transcript_id={transcript_id}")

# ----------------------------
# 5️⃣ Суммаризация (итоговый протокол)
# ----------------------------
async def process_summary(transcript_id: int, lang: str = "ru", format_: str = "json"):
    log.info(f"Запуск суммаризации для transcript_id={transcript_id}")
    async with async_session() as session:
        transcript = await session.get(MfgTranscript, transcript_id)
        if not transcript:
            log.error("Transcript %s not found", transcript_id)
            return
        try:
            transcript.status = "summary_processing"
            session.add(transcript)
            await session.commit()

            await generate_protocol(transcript_id, lang=lang, output_format=format_)

            transcript = await session.get(MfgTranscript, transcript_id)
            if transcript:
                transcript.status = "summary_done"
                session.add(transcript)
                await session.commit()
            log.info("Суммаризация завершена для transcript_id=%s", transcript_id)
        except Exception:
            # при ошибке пишем error
            transcript = await session.get(MfgTranscript, transcript_id)
            if transcript:
                transcript.status = "error"
                session.add(transcript)
                await session.commit()
            log.exception("Ошибка суммаризации для transcript_id=%s", transcript_id)
