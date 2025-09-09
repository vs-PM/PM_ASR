from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import (
    Column, BigInteger, String, Text, ForeignKey, Float, Date, Integer, func, Boolean, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP as PG_TIMESTAMP
from pgvector.sqlalchemy import Vector

Base = declarative_base()

class MfgTranscript(Base):
    __tablename__ = "mfg_transcript"
    id             = Column(BigInteger, primary_key=True, autoincrement=True)
    meeting_id     = Column(BigInteger, nullable=False)
    message_time   = Column(PG_TIMESTAMP(timezone=True))
    created_at     = Column(PG_TIMESTAMP(timezone=True), server_default=func.now())
    updated_at     = Column(PG_TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())
    processed_text = Column(Text)
    raw_text       = Column(Text)
    file_path      = Column(Text)
    mfg_id         = Column(String)
    filename       = Column(String)
    status         = Column(String, nullable=False)  # processing, diarization_done, transcription_done, embeddings_done, done, error

class MfgSegment(Base):
    __tablename__ = "mfg_segment"
    id            = Column(BigInteger, primary_key=True, autoincrement=True)
    transcript_id = Column(BigInteger, ForeignKey("mfg_transcript.id", ondelete="CASCADE"), nullable=False)
    speaker       = Column(String)
    start_ts      = Column(Float)   
    end_ts        = Column(Float)   
    text          = Column(Text)
    lang          = Column(String)  # ISO-код языка сегмента, опционально
    updated_at    = Column(PG_TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())
    __table_args__ = (
        UniqueConstraint("transcript_id", "start_ts", "end_ts", name="uq_mfg_segments_tid_range"),
    )

class MfgDiarization(Base):
    __tablename__ = "mfg_diarization"
    id            = Column(BigInteger, primary_key=True, autoincrement=True)
    transcript_id = Column(BigInteger, ForeignKey("mfg_transcript.id", ondelete="CASCADE"), nullable=False)
    speaker       = Column(String)
    start_ts      = Column(Float)
    end_ts        = Column(Float)
    file_path     = Column(Text)

class MfgEmbedding(Base):
    __tablename__ = "mfg_embedding"
    id         = Column(BigInteger, primary_key=True, autoincrement=True)
    segment_id = Column(BigInteger, ForeignKey("mfg_segment.id", ondelete="CASCADE"), nullable=False)
    embedding  = Column(Vector(768))  # Nomic Embed Text

class MfgSummarySection(Base):
    __tablename__ = "mfg_summary_section"
    id            = Column(BigInteger, primary_key=True, autoincrement=True)
    transcript_id = Column(BigInteger, ForeignKey("mfg_transcript.id", ondelete="CASCADE"), nullable=False)
    idx           = Column(Integer, nullable=False)  # порядок разделов в протоколе
    start_ts      = Column(Float)    # опционально: начальная метка времени раздела
    end_ts        = Column(Float)    # опционально: конечная метка времени раздела
    title         = Column(Text)     # заголовок раздела
    text          = Column(Text)     # содержимое раздела

class MfgActionItem(Base):
    __tablename__ = "mfg_action_item"
    id            = Column(BigInteger, primary_key=True, autoincrement=True)
    transcript_id = Column(BigInteger, ForeignKey("mfg_transcript.id", ondelete="CASCADE"), nullable=False)
    assignee      = Column(String)   # исполнитель
    due_date      = Column(Date)     # срок (может быть NULL)
    task          = Column(Text)     # формулировка задачи
    priority      = Column(String)   # опционально: приоритет

class MfgJob(Base):
    """
    Текущее состояние джобы по конкретному transcript_id.
    Если хотите поддержать несколько запусков — допускайте несколько строк на transcript_id
    (тогда уберите unique-индекс и добавьте поле run_id).
    """
    __tablename__ = "mfg_job"

    id            = Column(BigInteger, primary_key=True, autoincrement=True)
    transcript_id = Column(BigInteger, ForeignKey("mfg_transcript.id", ondelete="CASCADE"), nullable=False, index=True, unique=True)
    status        = Column(String(64), nullable=False, default="processing")  # те же строки, что и в MfgTranscript.status
    progress      = Column(Integer, nullable=False, default=0)                # 0..100
    step          = Column(String(128), nullable=True)                        # человекочитаемый шаг ("diarization", "asr"...)
    error         = Column(Text, nullable=True)

    worker_node   = Column(String(128), nullable=True)    # опционально: hostname/instance id
    attempt       = Column(Integer, nullable=False, default=1)
    started_at    = Column(PG_TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    finished_at   = Column(PG_TIMESTAMP(timezone=True), nullable=True)
    created_at    = Column(PG_TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at    = Column(PG_TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class MfgJobEvent(Base):
    """
    История смен статусов/прогресса для аудита и графиков.
    """
    __tablename__ = "mfg_job_event"

    id            = Column(BigInteger, primary_key=True, autoincrement=True)
    transcript_id = Column(BigInteger, ForeignKey("mfg_transcript.id", ondelete="CASCADE"), nullable=False, index=True)
    status        = Column(String(64), nullable=False)     # новое состояние
    progress      = Column(Integer, nullable=True)         # 0..100
    step          = Column(String(128), nullable=True)
    message       = Column(Text, nullable=True)
    created_at    = Column(PG_TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class MfgSpeaker(Base):
    """
    Справочник отображаемых имён/цветов для speaker-label'ов по транскрипту.
    """
    __tablename__ = "mfg_speaker"

    id            = Column(BigInteger, primary_key=True, autoincrement=True)
    transcript_id = Column(BigInteger, ForeignKey("mfg_transcript.id", ondelete="CASCADE"), nullable=False, index=True)
    speaker       = Column(String, nullable=False)         # 'SPEECH' / 'SPEAKER_00' / 'spk_0' и т.п.
    display_name  = Column(String, nullable=True)          # "Иван", "Оператор", ...
    color         = Column(String(16), nullable=True)      # "#RRGGBB"
    is_active     = Column(Boolean, nullable=False, default=True)
    created_at    = Column(PG_TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at    = Column(PG_TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
