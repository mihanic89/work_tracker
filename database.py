# database.py
import sqlite3

conn = sqlite3.connect("work_tracker.db", check_same_thread=False)
cursor = conn.cursor()

def init_db():
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        role TEXT DEFAULT 'employee'
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS work_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        start_time DATETIME,
        end_time DATETIME,
        start_location TEXT,
        end_location TEXT
    )
    """)
    conn.commit()

def get_user_role(user_id):
    cursor.execute("SELECT role FROM users WHERE user_id=?", (user_id,))
    result = cursor.fetchone()
    if not result:
        cursor.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()
        return 'employee'
    return result[0]

def set_user_role(user_id, role):
    cursor.execute("UPDATE users SET role=? WHERE user_id=?", (role, user_id))
    conn.commit()

def add_start_session(user_id, location):
    cursor.execute(
        "INSERT INTO work_sessions (user_id, start_time, start_location) VALUES (?, ?, ?)",
        (user_id, datetime.now(), location)
    )
    conn.commit()

def add_end_session(user_id, location):
    cursor.execute(
        "UPDATE work_sessions SET end_time=?, end_location=? WHERE user_id=? AND end_time IS NULL",
        (datetime.now(), location, user_id)
    )
    conn.commit()

def get_last_open_session(user_id):
    cursor.execute(
        "SELECT start_time FROM work_sessions WHERE user_id=? AND end_time IS NULL ORDER BY start_time DESC LIMIT 1",
        (user_id,)
    )
    return cursor.fetchone()

def get_sessions_by_month(user_id, month):
    cursor.execute(
        "SELECT * FROM work_sessions WHERE user_id=? AND start_time LIKE ?",
        (user_id, f"{month}%")
    )
    return cursor.fetchall()

def get_all_sessions_by_month(month):
    cursor.execute(
        "SELECT * FROM work_sessions WHERE start_time LIKE ?",
        (f"{month}%",)
    )
    return cursor.fetchall()

from datetime import datetime