from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from .config import DATABASE_URL
from .models import Base

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


from sqlalchemy import text, inspect

def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    # SQLite otomatik sütun migrasyonu (mevcut DB'yi bozmadan priority ve enabled ekle)
    try:
        with engine.connect() as conn:
            inspector = inspect(engine)
            if "providers" in inspector.get_table_names():
                cols = [c["name"] for c in inspector.get_columns("providers")]
                if "priority" not in cols:
                    conn.execute(text("ALTER TABLE providers ADD COLUMN priority INTEGER DEFAULT 0"))
                    conn.commit()
                if "enabled" not in cols:
                    conn.execute(text("ALTER TABLE providers ADD COLUMN enabled BOOLEAN DEFAULT 1"))
                    conn.commit()
    except Exception:
        pass



def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
