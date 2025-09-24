from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import (
    Column, BigInteger, String, Text, ForeignKey, Float, Date, Integer, func, Boolean, UniqueConstraint,
)
import enum
from sqlalchemy import Enum, Index
from sqlalchemy.dialects.postgresql import ARRAY
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
    file_id        = Column(BigInteger, ForeignKey("mfg_file.id", ondelete="SET NULL"), nullable=True)
    filename       = Column(String)
    status         = Column(String, nullable=False)  # processing, diarization_done, transcription_done, embeddings_done, done, error
    title          = Column(String, nullable=True)  # Название митинга (для UI)
    tags           = Column(ARRAY(String), nullable=True)  # Теги для фильтров в истории
    user_id        = Column(BigInteger, ForeignKey("mfg_user.id", ondelete="SET NULL"), nullable=True, index=True)

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


class UserRole(str, enum.Enum):
    admin = "admin"
    user  = "user"

class MfgUser(Base):
    __tablename__ = "mfg_user"

    id            = Column(BigInteger, primary_key=True, autoincrement=True)
    login         = Column(String(128), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role          = Column(Enum(UserRole, name="userrole"), nullable=False, server_default="user")
    is_active     = Column(Boolean, nullable=False, server_default="true")
    created_at    = Column(PG_TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

class MfgQA(Base):
    """
    Храним Q&A тред по конкретному протоколу.
    role: 'user' | 'assistant'
    refs: ссылки на сегменты/диапазоны, чтобы UI подсвечивал контекст.
    """
    __tablename__ = "mfg_qa"

    id            = Column(BigInteger, primary_key=True, autoincrement=True)
    transcript_id = Column(BigInteger, ForeignKey("mfg_transcript.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id       = Column(BigInteger, ForeignKey("mfg_user.id", ondelete="SET NULL"), nullable=True, index=True)
    role          = Column(String(16), nullable=False)  # 'user' | 'assistant'
    question      = Column(Text, nullable=True)
    answer        = Column(Text, nullable=True)
    refs          = Column(JSONB, nullable=True)        # например {"segments":[10,11]}
    created_at    = Column(PG_TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

class MfgAuditLog(Base):
    """
    Аудит действий (для админки).
    action: login/logout/upload/start_step/export и т.п.
    object_type: 'transcript'|'segment'|'user' etc.
    """
    __tablename__ = "mfg_audit_log"

    id          = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id     = Column(BigInteger, ForeignKey("mfg_user.id", ondelete="SET NULL"), nullable=True, index=True)
    action      = Column(String(64), nullable=False)
    object_type = Column(String(64), nullable=True)
    object_id   = Column(BigInteger, nullable=True, index=True)
    meta        = Column(JSONB, nullable=True)
    created_at  = Column(PG_TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

class RefreshToken(Base):
    """Hashed refresh tokens with rotation support."""
    __tablename__ = "auth_refresh_token"

    id          = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id     = Column(BigInteger, ForeignKey("mfg_user.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash  = Column(String(255), nullable=False)
    fingerprint = Column(String(64), nullable=False, unique=True, index=True)  # sha256 hex
    user_agent  = Column(String(256), nullable=True)
    ip          = Column(String(64), nullable=True)
    parent_id   = Column(BigInteger, ForeignKey("auth_refresh_token.id", ondelete="SET NULL"), nullable=True)
    expires_at  = Column(PG_TIMESTAMP(timezone=True), nullable=False)
    revoked_at  = Column(PG_TIMESTAMP(timezone=True), nullable=True)
    created_at  = Column(PG_TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

class MfgFile(Base):
    __tablename__ = "mfg_file"
    id          = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id     = Column(BigInteger, ForeignKey("mfg_user.id", ondelete="SET NULL"), index=True)
    filename    = Column(String, nullable=False)          # оригинальное имя
    stored_path = Column(Text, nullable=False)            # путь на диске
    size_bytes  = Column(BigInteger)
    mimetype    = Column(String)
    duration_s  = Column(Float)                           # если посчитаешь через ffprobe
    created_at  = Column(PG_TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

Index("ix_mfg_file_user_created", MfgFile.user_id, MfgFile.created_at.desc())
