import os
from dotenv import load_dotenv

from sqlalchemy import (
    create_engine,
    Table, Column, Integer, String, Text, TIMESTAMP, MetaData,
    PrimaryKeyConstraint, func
)
from sqlalchemy.orm import sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set. Check your .env file.")

# Engine
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

# Session (falls du es an anderen Stellen brauchst)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# -----------------------------
# SQLAlchemy Core Tables
# -----------------------------
metadata = MetaData()

kvstore = Table(
    "kvstore",
    metadata,
    Column("pid", String(17), nullable=False),
    Column("k", String(50), nullable=False),
    Column("side", Integer, nullable=False),
    Column("v", Text, nullable=False),
    Column("t", Text, nullable=True),
    PrimaryKeyConstraint("pid", "k", "side"),
)

vehicles = Table(
    "vehicles",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("side", String(15), nullable=False),
    Column("classname", String(40), nullable=False),
    Column("type", String(12), nullable=False),
    Column("pid", String(32), nullable=False),
    Column("alive", Integer, nullable=False, default=1),
    Column("active", Integer, nullable=False, default=1),
    Column("sold", Integer, nullable=False, default=0),
    Column("locked", Integer, nullable=False, default=0),
    Column("color", Integer, nullable=False, default=0),
    Column("trunk", Text, nullable=False),
    Column("chip", Integer, nullable=False, default=0),
    Column("ts_bought", TIMESTAMP, nullable=False),
    Column("ts_modified", TIMESTAMP, nullable=False),
)

support_cases = Table(
    "support_cases",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("player_pid", String(32), nullable=False),
    Column("player_name", String(128), nullable=True),

    Column("case_type", String(64), nullable=False),
    Column("area", String(64), nullable=False, server_default="Support"),
    Column("supporter_name", String(128), nullable=False),
    Column("scn", String(128), nullable=True),

    Column("content", Text, nullable=True),
    Column("status", String(32), nullable=False, server_default="open"),

    Column("created_at", TIMESTAMP, nullable=False, server_default=func.current_timestamp()),
    Column("updated_at", TIMESTAMP, nullable=False, server_default=func.current_timestamp(), onupdate=func.current_timestamp()),
)
