from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# SQLite for development — swap DATABASE_URL env var for PostgreSQL in production
SQLALCHEMY_DATABASE_URL = "sqlite:///./fullfit.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},  # Required for SQLite
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency: yields a DB session and ensures it is closed after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
