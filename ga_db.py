"""Module ga_db — extracted from grimeage_agent.py (behavior-preserving split)."""
import sqlite3
from ga_config import DB_PATH


def init_db():
    '''Initialize SQLite database for persistent analytics.'''
    conn = sqlite3.connect(DB_PATH)
    conn.execute('\n        CREATE TABLE IF NOT EXISTS sessions (\n            id INTEGER PRIMARY KEY AUTOINCREMENT,\n            char_id INTEGER NOT NULL,\n            started_at REAL NOT NULL,\n            ended_at REAL,\n            zone_id INTEGER,\n            kills INTEGER DEFAULT 0,\n            damage INTEGER DEFAULT 0,\n            healing INTEGER DEFAULT 0,\n            xp_gained INTEGER DEFAULT 0,\n            gold_gained INTEGER DEFAULT 0\n        )\n    ')
    conn.execute('\n        CREATE TABLE IF NOT EXISTS gear_snapshots (\n            id INTEGER PRIMARY KEY AUTOINCREMENT,\n            char_id INTEGER NOT NULL,\n            timestamp REAL NOT NULL,\n            slot TEXT NOT NULL,\n            item_name TEXT NOT NULL,\n            rarity TEXT,\n            p_atk INTEGER DEFAULT 0,\n            m_atk INTEGER DEFAULT 0,\n            p_def INTEGER DEFAULT 0,\n            m_def INTEGER DEFAULT 0\n        )\n    ')
    conn.execute('\n        CREATE TABLE IF NOT EXISTS gold_history (\n            id INTEGER PRIMARY KEY AUTOINCREMENT,\n            char_id INTEGER NOT NULL,\n            timestamp REAL NOT NULL,\n            gold INTEGER NOT NULL\n        )\n    ')
    conn.execute("\n        CREATE TABLE IF NOT EXISTS progression_markers (\n            id INTEGER PRIMARY KEY AUTOINCREMENT,\n            char_id INTEGER NOT NULL,\n            timestamp REAL NOT NULL,\n            event_type TEXT NOT NULL,  -- 'level_up', 'gear_upgrade', 'ascend', 'zone_move'\n            detail TEXT\n        )\n    ")
    conn.commit()
    return conn

