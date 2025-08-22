# app/background.py
import os
import torch
from app.services.asr_service import transcribe_with_diarization
from app.database import get_pool

async def process_and_save(audio_path: str, record_id: int):
    async with get_pool().__aenter__() as pool:
        try:
            segments = await transcribe_with_diarization(audio_path)

            async with pool.acquire() as conn:
                # статус
                await conn.execute("UPDATE transcripts SET status='done' WHERE id=$1", record_id)
                # вставка сегментов
                await conn.executemany(
                    """
                    INSERT INTO segments
                        (transcript_id, speaker, start_ts, end_ts, text, embedding)
                    VALUES
                        ($1, $2, $3, $4, $5, $6)
                    """,
                    [(record_id, s["speaker"], s["start_ts"], s["end_ts"],
                      s["text"], s["embedding"]) for s in segments]
                )
        except Exception as exc:
            async with pool.acquire() as conn:
                await conn.execute("UPDATE transcripts SET status='error' WHERE id=$1", record_id)
            raise exc
        finally:
            os.remove(audio_path)
            torch.cuda.empty_cache()
            await get_pool().__aexit__(None, None, None)
