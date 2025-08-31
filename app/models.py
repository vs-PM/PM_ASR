from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, BigInteger, String, Text, ForeignKey, Float, func
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
    start_ts      = Column(Float)   # изменено на Float
    end_ts        = Column(Float)   # изменено на Float
    text          = Column(Text)

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
