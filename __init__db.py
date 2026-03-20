from sqlalchemy import text
from database import engine
from models import Base

# Create all tables (only creates tables that don't exist; does not add columns to existing tables)
Base.metadata.create_all(bind=engine)

# Add missing columns to existing tables (fix for DBs created with older schema)
# create_all() only creates tables; it does not add columns to existing tables.
_migrations = [
    ("users", "email", "VARCHAR(255) UNIQUE"),
    ("group_memberships", "invite_token", "VARCHAR(255) UNIQUE"),
    ("group_memberships", "accepted", "BOOLEAN DEFAULT FALSE"),
    ("group_memberships", "joined_at", "TIMESTAMP WITH TIME ZONE DEFAULT NOW()"),
]
try:
    with engine.connect() as conn:
        for table, column, col_type in _migrations:
            try:
                conn.execute(text(
                    f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {col_type}"
                ))
            except Exception as e:
                if "already exists" not in str(e).lower():
                    print(f"Note: Could not add {table}.{column}:", e)
        conn.commit()
except Exception as e:
    print("Note: Schema migration warning:", e)

print("Database tables created / updated.")
