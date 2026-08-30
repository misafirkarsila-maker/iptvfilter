from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Provider(Base):
    """Kaydedilmiş Xtream sağlayıcı hesabı."""
    __tablename__ = "providers"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    server_url = Column(String(500), nullable=False)  # ör: http://host:8080
    username = Column(String(255), nullable=False)
    password_enc = Column(Text, nullable=False)  # şifrelenmiş
    created_at = Column(DateTime, default=datetime.utcnow)
    last_sync_at = Column(DateTime, nullable=True)
    last_sync_status = Column(String(50), default="never")  # ok | error | never
    last_sync_error = Column(Text, nullable=True)
    # Stream URL adapter
    adapter_type = Column(String(50), default="standard")
    adapter_config = Column(Text, nullable=True)  # JSON string
    # Öncelik ve aktiflik (Aggregation)
    priority = Column(Integer, default=0)  # küçük sayı = yüksek öncelik
    enabled = Column(Boolean, default=True)  # birleştirmede aktif/pasif

    categories = relationship(
        "Category", back_populates="provider", cascade="all, delete-orphan"
    )
    streams = relationship(
        "Stream", back_populates="provider", cascade="all, delete-orphan"
    )
    epg_programs = relationship(
        "EpgProgram", back_populates="provider", cascade="all, delete-orphan"
    )

    @property
    def display_host(self):
        return self.server_url.split("//")[-1].rstrip("/")


class Category(Base):
    """Sağlayıcının kategori yapısı. content_type: live|vod|series."""
    __tablename__ = "categories"
    __table_args__ = (
        UniqueConstraint(
            "provider_id", "content_type", "provider_category_id",
            name="uq_category_provider",
        ),
        Index("idx_categories_lookup", "provider_id", "content_type", "enabled", "is_active"),
    )

    id = Column(Integer, primary_key=True)
    provider_id = Column(Integer, ForeignKey("providers.id"), nullable=False)
    content_type = Column(String(10), nullable=False)  # live|vod|series
    provider_category_id = Column(String(255), default="")  # sağlayıcının kendi id'si
    name = Column(String(300), nullable=False)
    parent_name = Column(String(300), nullable=True)  # sağlayıcı gruplaşıyorsa
    sort_order = Column(Integer, default=0)  # sağlayıcının sıralaması

    # Filtreleme durumu (kullanıcı seçimi)
    enabled = Column(Boolean, default=False)  # aktif kategori
    is_new = Column(Boolean, default=False)  # yeni keşfedilen (varsayılan pasif)
    # Yumuşak silme / kullanım takibi
    is_active = Column(Boolean, default=True)  # sağlayıcı hâlâ gönderiyor mu
    last_seen_at = Column(DateTime, nullable=True)

    provider = relationship("Provider", back_populates="categories")
    streams = relationship(
        "Stream", back_populates="category", lazy="selectin"
    )


class Stream(Base):
    """Tek bir içerik öğesi (kanal/film/dizi). content_type: live|vod|series."""
    __tablename__ = "streams"
    __table_args__ = (
        UniqueConstraint(
            "provider_id", "content_type", "provider_stream_id",
            name="uq_stream_provider",
        ),
        Index("idx_streams_lookup", "provider_id", "content_type", "enabled", "is_active"),
        Index("idx_streams_prov_sid", "provider_stream_id"),
    )

    id = Column(Integer, primary_key=True)
    provider_id = Column(Integer, ForeignKey("providers.id"), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    content_type = Column(String(10), nullable=False)  # live|vod|series|movie
    provider_stream_id = Column(String(255), default="")
    name = Column(String(500), nullable=False)
    # Sağlayıcının kategori id'si (kategori tablosuna referans denormalize)
    provider_category_id = Column(String(255), default="")

    # Sağlayıcı metadata (future item-level filtering)
    stream_icon = Column(Text, nullable=True)
    stream_url_path = Column(Text, nullable=True)  # /live/u/p/id.ts gibi
    stream_source = Column(String(30), default="xtream")  # m3u|xtream
    extension = Column(String(20), nullable=True)
    container = Column(String(20), nullable=True)
    rating = Column(Float, nullable=True)
    year = Column(String(10), nullable=True)
    description = Column(Text, nullable=True)
    added_at = Column(String(20), nullable=True)

    # Gelecek sürüm: içerik bazlı seçim
    enabled = Column(Boolean, default=True)  # kategori filtresine bağlı
    manual_enabled = Column(Boolean, nullable=True)  # item-level (ileride)

    is_active = Column(Boolean, default=True)
    last_seen_at = Column(DateTime, nullable=True)

    provider = relationship("Provider", back_populates="streams")
    category = relationship("Category", back_populates="streams")


class EpgProgram(Base):
    """EPG program kayıtları."""
    __tablename__ = "epg_programs"
    __table_args__ = (
        UniqueConstraint(
            "provider_id", "channel_id", "start",
            name="uq_epg_program",
        ),
    )

    id = Column(Integer, primary_key=True)
    provider_id = Column(Integer, ForeignKey("providers.id"), nullable=False)
    stream_id = Column(Integer, ForeignKey("streams.id"), nullable=True)
    channel_id = Column(String(255), default="")  # sağlayıcının channel id'si
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    start = Column(DateTime, nullable=False)  # UTC
    end = Column(DateTime, nullable=False)
    is_active = Column(Boolean, default=True)
    last_seen_at = Column(DateTime, nullable=True)

    provider = relationship("Provider", back_populates="epg_programs")
    stream = relationship("Stream")
