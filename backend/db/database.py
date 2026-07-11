import os
from sqlmodel import create_engine, Session

# Fallback to a local sqlite database for development if POSTGRES_URL isn't provided
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./incident_mesh.db")

# If using PostgreSQL, we need to adapt the connection string slightly for SQLAlchemy
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {"check_same_thread": False} if "sqlite" in DATABASE_URL else {}

engine = create_engine(DATABASE_URL, echo=True, connect_args=connect_args)

def get_session():
    with Session(engine) as session:
        yield session
