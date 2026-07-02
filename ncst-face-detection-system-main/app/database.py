import sqlite3
import threading
from datetime import datetime
from pathlib import Path

import bcrypt as _bcrypt

from app.config import settings
from app.utils import get_pst_now

DB_PATH = Path(settings.database_path)


def pst_now() -> datetime:
    return get_pst_now()


def pst_str(dt: datetime | None = None) -> str:
    return (dt if dt else pst_now()).strftime("%Y-%m-%d %H:%M:%S")


_local = threading.local()


def get_db_connection() -> sqlite3.Connection:
    conn = getattr(_local, "connection", None)
    if conn is None:
        conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        _local.connection = conn
    return conn


def init_db():
    conn = get_db_connection()
    conn.executescript("""
        DROP TABLE IF EXISTS attendance_logs;
        DROP TABLE IF EXISTS students;

        CREATE TABLE IF NOT EXISTS admins (
            admin_id                TEXT PRIMARY KEY,
            email                   TEXT UNIQUE NOT NULL,
            password_hash           TEXT NOT NULL,
            first_name              TEXT NOT NULL,
            last_name               TEXT NOT NULL,
            created_at              TIMESTAMP,
            reset_password_token    TEXT,
            reset_password_expires  TIMESTAMP,
            is_approved             INTEGER NOT NULL DEFAULT 0,
            approval_status         TEXT NOT NULL DEFAULT 'pending'
                CHECK(approval_status IN ('pending', 'approved', 'rejected'))
        );

        CREATE TABLE IF NOT EXISTS registrants (
            user_id             TEXT PRIMARY KEY,
            first_name          TEXT NOT NULL,
            last_name           TEXT NOT NULL,
            role                TEXT NOT NULL CHECK(role IN ('STUDENT','STAFF','FACULTY')),
            department_section  TEXT NOT NULL,
            face_embedding      BLOB,
            status              TEXT NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE','ARCHIVED')),
            created_at          TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS attendance_logs (
            log_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     TEXT NOT NULL REFERENCES registrants(user_id),
            logged_at   TIMESTAMP,
            device_id   TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS audit_logs (
            log_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_email TEXT,
            action      TEXT NOT NULL,
            details     TEXT,
            logged_at   TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS password_otps (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            email       TEXT NOT NULL,
            otp_hash    TEXT NOT NULL,
            expires_at  TIMESTAMP NOT NULL,
            created_at  TIMESTAMP NOT NULL,
            purpose     TEXT NOT NULL DEFAULT 'password_reset'
        );
    """)
    conn.commit()
    _migrate_password_otps(conn)
    _migrate_admins(conn)
    _ensure_main_admin(conn)


def _migrate_admins(conn: sqlite3.Connection):
    columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(admins)").fetchall()
    }
    if "reset_password_token" not in columns:
        conn.execute("ALTER TABLE admins ADD COLUMN reset_password_token TEXT")
    if "reset_password_expires" not in columns:
        conn.execute("ALTER TABLE admins ADD COLUMN reset_password_expires TIMESTAMP")
    if "is_approved" not in columns:
        conn.execute("ALTER TABLE admins ADD COLUMN is_approved INTEGER NOT NULL DEFAULT 0")
        conn.execute(
            "ALTER TABLE admins ADD COLUMN approval_status TEXT NOT NULL DEFAULT 'pending'"
        )
        conn.execute(
            "UPDATE admins SET is_approved = 1, approval_status = 'approved'"
        )
    conn.commit()


def _migrate_password_otps(conn: sqlite3.Connection):
    columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(password_otps)").fetchall()
    }
    if "purpose" not in columns:
        conn.execute(
            "ALTER TABLE password_otps ADD COLUMN purpose TEXT NOT NULL DEFAULT 'password_reset'"
        )
        conn.commit()


MAIN_ADMIN_ID = "admin"
MAIN_ADMIN_PASSWORD = "NCST 2026"


def _ensure_main_admin(conn: sqlite3.Connection):
    main_email = settings.main_admin_email.strip().lower()
    new_hash = _bcrypt.hashpw(
        MAIN_ADMIN_PASSWORD.encode(), _bcrypt.gensalt()
    ).decode()

    by_id = conn.execute(
        "SELECT admin_id, email, password_hash FROM admins WHERE admin_id = ?",
        (MAIN_ADMIN_ID,),
    ).fetchone()
    by_email = conn.execute(
        "SELECT admin_id, email, password_hash FROM admins WHERE email = ?",
        (main_email,),
    ).fetchone()

    if by_email:
        needs_password_update = _bcrypt.checkpw(
            b"admin123", by_email["password_hash"].encode()
        )
        password_hash = new_hash if needs_password_update else by_email["password_hash"]
        if by_email["admin_id"] != MAIN_ADMIN_ID and by_id:
            conn.execute("DELETE FROM admins WHERE admin_id = ?", (MAIN_ADMIN_ID,))
        if by_email["admin_id"] != MAIN_ADMIN_ID or needs_password_update:
            conn.execute(
                """
                UPDATE admins
                SET admin_id = ?, password_hash = ?, first_name = ?, last_name = ?,
                    is_approved = 1, approval_status = 'approved'
                WHERE email = ?
                """,
                (MAIN_ADMIN_ID, password_hash, "Paul", "Lacuesta", main_email),
            )
            conn.commit()
        return

    if by_id:
        needs_password_update = _bcrypt.checkpw(
            b"admin123", by_id["password_hash"].encode()
        )
        password_hash = new_hash if needs_password_update else by_id["password_hash"]
        conn.execute(
            """
            UPDATE admins
            SET email = ?, password_hash = ?, first_name = ?, last_name = ?,
                is_approved = 1, approval_status = 'approved'
            WHERE admin_id = ?
            """,
            (main_email, password_hash, "Paul", "Lacuesta", MAIN_ADMIN_ID),
        )
        conn.commit()
        return

    conn.execute(
        """
        INSERT INTO admins (
            admin_id, email, password_hash, first_name, last_name, created_at,
            is_approved, approval_status
        )
        VALUES (?, ?, ?, ?, ?, ?, 1, 'approved')
        """,
        (MAIN_ADMIN_ID, main_email, new_hash, "Paul", "Lacuesta", pst_str()),
    )
    conn.commit()


def log_system_action(admin_email: str | None, action: str, details: str | None = None):
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO audit_logs (admin_email, action, details, logged_at) VALUES (?, ?, ?, ?)",
        (admin_email, action, details, pst_str()),
    )
    conn.commit()


def get_admin_email(admin_id: str) -> str | None:
    conn = get_db_connection()
    row = conn.execute("SELECT email FROM admins WHERE admin_id = ?", (admin_id,)).fetchone()
    return row["email"] if row else None
