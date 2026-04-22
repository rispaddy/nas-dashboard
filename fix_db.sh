#!/usr/bin/env python3
"""Fix database schema migration - add missing tables to existing dashboard.db"""
import sqlite3, os

# Path to dashboard.db on NAS (via docker volume)
DB_PATH = os.environ.get("DB_PATH", "/var/services/homes/Victor/nas-dashboard/data/dashboard.db")

# We can't write directly to NAS filesystem, so create a SQL patch script
sql = """
-- Add missing tables if they don't exist

-- Tasks table (ensure updated_at column exists)
CREATE TABLE IF NOT EXISTS _tasks_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT UNIQUE,
    content TEXT,
    status TEXT DEFAULT 'pending',
    priority INTEGER DEFAULT 0,
    due_date TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Migrate data if old 'tasks' table exists
INSERT OR IGNORE INTO _tasks_new (task_id, content, status, priority, due_date)
SELECT task_id, content, status, priority, due_date FROM tasks;

DROP TABLE IF EXISTS tasks;
ALTER TABLE _tasks_new RENAME TO tasks;

-- Polymarket positions table
CREATE TABLE IF NOT EXISTS _pm_pos_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    market_slug TEXT UNIQUE,
    market_question TEXT,
    side TEXT,
    entry_price REAL,
    qty REAL,
    cost REAL,
    current_price REAL,
    current_value REAL,
    pnl REAL,
    pnl_pct REAL,
    status TEXT DEFAULT 'open',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO _pm_pos_new (market_slug, market_question, side, entry_price, qty, cost, current_price, current_value, pnl, pnl_pct, status)
SELECT slug, question, side, entry_price, qty, cost, current_price, current_value, pnl, pnl_pct, status FROM positions;

DROP TABLE IF EXISTS positions;
ALTER TABLE _pm_pos_new RENAME TO positions;

-- Polymarket watchlist table
CREATE TABLE IF NOT EXISTS _pm_wl_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    market_slug TEXT UNIQUE,
    market_question TEXT,
    current_price REAL,
    trend TEXT,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO _pm_wl_new (market_slug, market_question, current_price, trend)
SELECT slug, question, current_price, trend FROM watchlist;

DROP TABLE IF EXISTS watchlist;
ALTER TABLE _pm_wl_new RENAME TO watchlist;

-- Polymarket trades table
CREATE TABLE IF NOT EXISTS _pm_trades_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id TEXT UNIQUE,
    market_slug TEXT,
    market_question TEXT,
    side TEXT,
    price REAL,
    qty REAL,
    total_cost REAL,
    trade_date TEXT,
    notes TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO _pm_trades_new (trade_id, market_slug, market_question, side, price, qty, total_cost, trade_date, notes)
SELECT trade_id, slug, question, side, price, qty, total_cost, trade_date, notes FROM trades;

DROP TABLE IF EXISTS trades;
ALTER TABLE _pm_trades_new RENAME TO trades;
"""

print("SQL Migration Script (run on NAS):")
print("=" * 50)
print(sql)
print("=" * 50)
print(f"\nRun on NAS with:")
print(f"  sqlite3 {DB_PATH} << 'EOF'")
print(sql)
print("EOF")
