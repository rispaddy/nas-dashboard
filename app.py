#!/usr/bin/env python3
"""
NAS Dashboard - Paddy Personal Dashboard
Flask app with Summary, Sales, and Polymarket pages.
"""

import sqlite3
import os
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify, request

app = Flask(__name__)
app.template_folder = 'templates'
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get('DATA_DIR', os.path.join(BASE_DIR, 'data'))
DB_PATH = os.environ.get('DB_PATH', os.path.join(DATA_DIR, 'dashboard.db'))


def get_db():
    """Get SQLite database connection with thread-safe settings."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    # Allow multi-threaded access
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """Initialize database schema."""
    conn = get_db()
    c = conn.cursor()

    # Tasks table
    c.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            due_date TEXT,
            status TEXT DEFAULT 'pending',
            priority TEXT DEFAULT 'normal',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Calendar events table
    c.execute('''
        CREATE TABLE IF NOT EXISTS calendar_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            event_date TEXT NOT NULL,
            event_time TEXT,
            event_type TEXT DEFAULT 'appointment',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Cron jobs table
    c.execute('''
        CREATE TABLE IF NOT EXISTS cron_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            schedule TEXT NOT NULL,
            description TEXT,
            last_run TEXT,
            next_run TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Sales records table
    c.execute('''
        CREATE TABLE IF NOT EXISTS sales_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            sales_no TEXT,
            subordinate TEXT NOT NULL,
            sold_amount REAL,
            net_price REAL,
            deposit_pct TEXT,
            volume_credits INTEGER,
            commission_rule TEXT,
            manager_commission REAL,
            status TEXT DEFAULT 'completed',
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Sales KPIs table (monthly summary)
    c.execute('''
        CREATE TABLE IF NOT EXISTS sales_kpis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            month_label TEXT NOT NULL,
            total_volume REAL,
            total_commission REAL,
            total_deals INTEGER,
            agent_name TEXT,
            agent_volume REAL,
            agent_credits INTEGER,
            agent_net REAL,
            agent_commission REAL,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Polymarket positions table
    c.execute('''
        CREATE TABLE IF NOT EXISTS polymarket_positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            market_slug TEXT UNIQUE NOT NULL,
            market_question TEXT,
            qty REAL,
            cost REAL,
            current_price REAL,
            current_value REAL,
            pnl REAL,
            pnl_pct REAL,
            status TEXT DEFAULT 'open',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Polymarket watchlist table
    c.execute('''
        CREATE TABLE IF NOT EXISTS polymarket_watchlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            market_slug TEXT UNIQUE NOT NULL,
            market_question TEXT,
            current_price REAL,
            trend TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Polymarket trades history
    c.execute('''
        CREATE TABLE IF NOT EXISTS polymarket_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            market_slug TEXT NOT NULL,
            action TEXT NOT NULL,
            price REAL,
            qty REAL,
            total_cost REAL,
            trade_date TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Projects table
    c.execute('''
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'active',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Data retention - auto-delete records older than 14 days
    c.execute('''
        CREATE TABLE IF NOT EXISTS sync_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sync_type TEXT NOT NULL,
            status TEXT,
            records_synced INTEGER,
            synced_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    conn.commit()
    conn.close()
    print("[OK] Database initialized")


# ── Routes ──────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    """Redirect to summary page."""
    return render_template('summary.html')


@app.route('/summary')
def summary():
    """Summary page - tasks, calendar, cron, projects."""
    conn = get_db()
    c = conn.cursor()

    # Get upcoming tasks (next 14 days)
    today = datetime.now().strftime('%Y-%m-%d')
    two_weeks = (datetime.now() + timedelta(days=14)).strftime('%Y-%m-%d')
    c.execute('''
        SELECT * FROM tasks
        WHERE due_date BETWEEN ? AND ?
        AND status != 'completed'
        ORDER BY due_date ASC, priority DESC
    ''', (today, two_weeks))
    upcoming_tasks = [dict(row) for row in c.fetchall()]

    # Get overdue tasks
    c.execute('''
        SELECT * FROM tasks
        WHERE due_date < ? AND status != 'completed'
        ORDER BY due_date ASC
    ''', (today,))
    overdue_tasks = [dict(row) for row in c.fetchall()]

    # Get upcoming calendar events (next 14 days)
    c.execute('''
        SELECT * FROM calendar_events
        WHERE event_date BETWEEN ? AND ?
        ORDER BY event_date ASC, event_time ASC
    ''', (today, two_weeks))
    upcoming_events = [dict(row) for row in c.fetchall()]

    # Get active cron jobs
    c.execute('SELECT * FROM cron_jobs WHERE is_active = 1 ORDER BY name ASC')
    active_crons = [dict(row) for row in c.fetchall()]

    # Get recent projects
    c.execute('SELECT * FROM projects WHERE status = "active" ORDER BY updated_at DESC')
    active_projects = [dict(row) for row in c.fetchall()]

    # Get stats
    c.execute('SELECT COUNT(*) as cnt FROM tasks WHERE status != "completed"')
    pending_tasks_count = c.fetchone()['cnt']

    c.execute('SELECT COUNT(*) as cnt FROM calendar_events WHERE event_date >= ?', (today,))
    upcoming_events_count = c.fetchone()['cnt']

    c.execute('SELECT COUNT(*) as cnt FROM cron_jobs WHERE is_active = 1')
    active_crons_count = c.fetchone()['cnt']

    conn.close()

    return render_template('summary.html',
        upcoming_tasks=upcoming_tasks,
        overdue_tasks=overdue_tasks,
        upcoming_events=upcoming_events,
        active_crons=active_crons,
        active_projects=active_projects,
        pending_tasks_count=pending_tasks_count,
        upcoming_events_count=upcoming_events_count,
        active_crons_count=active_crons_count,
        today=today
    )


@app.route('/sales')
def sales():
    """Sales summary page."""
    conn = get_db()
    c = conn.cursor()

    # Get monthly KPIs
    c.execute('SELECT * FROM sales_kpis ORDER BY month_label DESC LIMIT 1')
    row = c.fetchone()
    latest_kpi = dict(row) if row else None

    # Get all KPIs for chart
    c.execute('SELECT * FROM sales_kpis ORDER BY month_label ASC')
    all_kpis = [dict(row) for row in c.fetchall()]

    # Get recent sales records (last 14 days)
    two_weeks_ago = (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d')
    c.execute('''
        SELECT * FROM sales_records
        WHERE date >= ?
        ORDER BY date DESC, id DESC
    ''', (two_weeks_ago,))
    recent_sales = [dict(row) for row in c.fetchall()]

    # Get agent breakdown
    c.execute('''
        SELECT subordinate,
               COUNT(*) as deals,
               SUM(sold_amount) as volume,
               SUM(manager_commission) as commission
        FROM sales_records
        WHERE date >= ?
        GROUP BY subordinate
        ORDER BY volume DESC
    ''', (two_weeks_ago,))
    agent_breakdown = [dict(row) for row in c.fetchall()]

    conn.close()

    return render_template('sales.html',
        latest_kpi=latest_kpi,
        all_kpis=all_kpis,
        recent_sales=recent_sales,
        agent_breakdown=agent_breakdown
    )


@app.route('/polymarket')
def polymarket():
    """Polymarket details page."""
    conn = get_db()
    c = conn.cursor()

    # Get open positions
    c.execute('SELECT * FROM polymarket_positions WHERE status = "open" ORDER BY updated_at DESC')
    positions = []
    for row in c.fetchall():
        p = {}
        for key in ['market_slug', 'market_question', 'qty', 'cost', 'current_price', 'current_value', 'pnl', 'pnl_pct', 'status']:
            val = row[key]
            if val is None:
                val = 0 if key in ['qty', 'cost', 'current_price', 'current_value', 'pnl', 'pnl_pct'] else ''
            p[key] = val
        positions.append(p)

    # Get watchlist
    c.execute('SELECT * FROM polymarket_watchlist ORDER BY updated_at DESC')
    watchlist = []
    for row in c.fetchall():
        w = {}
        for key in ['market_slug', 'market_question', 'current_price', 'trend']:
            val = row[key]
            if val is None:
                val = 0 if key == 'current_price' else ''
            w[key] = val
        watchlist.append(w)

    # Get recent trades
    c.execute('SELECT * FROM polymarket_trades ORDER BY created_at DESC LIMIT 10')
    trades = []
    for row in c.fetchall():
        t = {}
        for key in ['market_slug', 'action', 'price', 'qty', 'total_cost', 'trade_date', 'created_at']:
            val = row[key]
            if val is None:
                val = 0 if key in ['price', 'qty', 'total_cost'] else ''
            t[key] = val
        trades.append(t)

    # Calculate totals
    total_cost = sum(p['cost'] for p in positions)
    total_value = sum(p['current_value'] for p in positions)
    total_pnl = sum(p['pnl'] for p in positions)

    conn.close()

    return render_template('polymarket.html',
        positions=positions,
        watchlist=watchlist,
        trades=trades,
        total_cost=total_cost,
        total_value=total_value,
        total_pnl=total_pnl
    )


# ── API Endpoints ────────────────────────────────────────────────────────────

@app.route('/api/tasks', methods=['POST'])
def api_tasks():
    """Receive tasks data from Hermes sync."""
    data = request.json
    tasks = data.get('tasks', [])
    conn = get_db()
    c = conn.cursor()

    # Clear old tasks and insert new
    c.execute('DELETE FROM tasks')
    for task in tasks:
        c.execute('''
            INSERT INTO tasks (title, description, due_date, status, priority)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            task.get('title', ''),
            task.get('description', ''),
            task.get('due_date', ''),
            task.get('status', 'pending'),
            task.get('priority', 'normal')
        ))

    conn.commit()
    conn.close()
    return jsonify({'status': 'ok', 'tasks_synced': len(tasks)})


@app.route('/api/calendar', methods=['POST'])
def api_calendar():
    """Receive calendar events from Hermes sync."""
    data = request.json
    events = data.get('events', [])
    conn = get_db()
    c = conn.cursor()

    c.execute('DELETE FROM calendar_events')
    for event in events:
        c.execute('''
            INSERT INTO calendar_events (title, description, event_date, event_time, event_type)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            event.get('title', ''),
            event.get('description', ''),
            event.get('event_date', ''),
            event.get('event_time', ''),
            event.get('event_type', 'appointment')
        ))

    conn.commit()
    conn.close()
    return jsonify({'status': 'ok', 'events_synced': len(events)})


@app.route('/api/cron', methods=['POST'])
def api_cron():
    """Receive cron jobs data from Hermes sync."""
    data = request.json
    crons = data.get('cron_jobs', [])
    conn = get_db()
    c = conn.cursor()

    c.execute('DELETE FROM cron_jobs')
    for cron in crons:
        # Ensure all values are strings or basic types
        description = str(cron.get('description', ''))[:200] if cron.get('description') else ''
        c.execute('''
            INSERT INTO cron_jobs (name, schedule, description, last_run, next_run, is_active)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            str(cron.get('name', ''))[:100],
            str(cron.get('schedule', ''))[:50],
            description,
            str(cron.get('last_run', ''))[:50],
            str(cron.get('next_run', ''))[:50],
            int(cron.get('is_active', 1))
        ))

    conn.commit()
    conn.close()
    return jsonify({'status': 'ok', 'crons_synced': len(crons)})


@app.route('/api/projects', methods=['POST'])
def api_projects():
    """Receive projects data from Hermes sync."""
    data = request.json
    projects = data.get('projects', [])
    conn = get_db()
    c = conn.cursor()

    c.execute('DELETE FROM projects')
    for proj in projects:
        c.execute('''
            INSERT INTO projects (name, description, status)
            VALUES (?, ?, ?)
        ''', (
            str(proj.get('name', ''))[:100],
            str(proj.get('description', ''))[:500] if proj.get('description') else '',
            str(proj.get('status', 'active'))[:20]
        ))

    conn.commit()
    conn.close()
    return jsonify({'status': 'ok', 'projects_synced': len(projects)})


@app.route('/api/sales/summary', methods=['POST'])
def api_sales_summary():
    """Receive sales KPIs from Hermes sync."""
    data = request.json
    conn = get_db()
    c = conn.cursor()

    c.execute('DELETE FROM sales_kpis')
    total = data.get('total', {})

    # Insert agent-level KPIs
    agents = total.get('agents', [])
    month = total.get('month', '')

    for agent in agents:
        c.execute('''
            INSERT INTO sales_kpis
            (month_label, agent_name, agent_volume, agent_credits, agent_net, agent_commission)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            month,
            agent.get('name', ''),
            agent.get('volume', 0),
            agent.get('credits', 0),
            agent.get('net', 0),
            agent.get('commission', 0)
        ))

    # Insert total KPIs
    c.execute('''
        INSERT INTO sales_kpis
        (month_label, total_volume, total_commission, total_deals)
        VALUES (?, ?, ?, ?)
    ''', (
        month,
        total.get('volume', 0),
        total.get('commission', 0),
        total.get('deals', 0)
    ))

    conn.commit()
    conn.close()
    return jsonify({'status': 'ok'})


@app.route('/api/sales/deals', methods=['POST'])
def api_sales_deals():
    """Receive sales deals from Hermes sync."""
    data = request.json
    deals = data if isinstance(data, list) else []
    conn = get_db()
    c = conn.cursor()

    # Keep only last 14 days
    cutoff = (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d')
    c.execute('DELETE FROM sales_records WHERE date < ?', (cutoff,))

    for deal in deals:
        c.execute('''
            INSERT OR REPLACE INTO sales_records
            (date, sales_no, subordinate, sold_amount, net_price, deposit_pct,
             volume_credits, commission_rule, manager_commission, status, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            deal.get('date', ''),
            deal.get('sales_no', ''),
            deal.get('subordinate', ''),
            deal.get('sold_amount', 0),
            deal.get('net_price', 0),
            deal.get('deposit_pct', ''),
            deal.get('volume_credits', 0),
            deal.get('commission_rule', ''),
            deal.get('manager_commission', 0),
            deal.get('status', 'completed'),
            deal.get('notes', '')
        ))

    conn.commit()
    conn.close()
    return jsonify({'status': 'ok', 'deals_synced': len(deals)})


@app.route('/api/portfolio', methods=['POST'])
def api_portfolio():
    """Receive Polymarket portfolio from Hermes sync."""
    data = request.json
    conn = get_db()
    c = conn.cursor()

    # Clear old positions and insert new
    c.execute('DELETE FROM polymarket_positions')

    positions = data.get('positions', [])
    for pos in positions:
        c.execute('''
            INSERT INTO polymarket_positions
            (market_slug, market_question, qty, cost, current_price, current_value, pnl, pnl_pct, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            pos.get('slug', ''),
            pos.get('question', ''),
            pos.get('qty', 0),
            pos.get('cost', 0),
            pos.get('current_price', 0),
            pos.get('current_value', 0),
            pos.get('pnl', 0),
            pos.get('pnl_pct', 0),
            'open'
        ))

    conn.commit()
    conn.close()
    return jsonify({'status': 'ok', 'positions_synced': len(positions)})


@app.route('/api/watchlist', methods=['POST'])
def api_watchlist():
    """Receive Polymarket watchlist from Hermes sync."""
    data = request.json
    watchlist = data.get('watchlist', [])
    conn = get_db()
    c = conn.cursor()

    c.execute('DELETE FROM polymarket_watchlist')
    for item in watchlist:
        c.execute('''
            INSERT INTO polymarket_watchlist
            (market_slug, market_question, current_price, trend)
            VALUES (?, ?, ?, ?)
        ''', (
            item.get('slug', ''),
            item.get('question', ''),
            item.get('current_price', 0),
            item.get('trend', '')
        ))

    conn.commit()
    conn.close()
    return jsonify({'status': 'ok', 'watchlist_synced': len(watchlist)})


@app.route('/api/trades', methods=['POST'])
def api_trades():
    """Receive Polymarket trade history from Hermes sync."""
    data = request.json
    trades = data.get('trades', [])
    conn = get_db()
    c = conn.cursor()

    for trade in trades:
        c.execute('''
            INSERT INTO polymarket_trades
            (market_slug, action, price, qty, total_cost, trade_date)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            trade.get('slug', ''),
            trade.get('action', ''),
            trade.get('price', 0),
            trade.get('qty', 0),
            trade.get('total_cost', 0),
            trade.get('date', '')
        ))

    # Keep only last 50 trades
    c.execute('''
        DELETE FROM polymarket_trades
        WHERE id NOT IN (
            SELECT id FROM polymarket_trades ORDER BY created_at DESC LIMIT 50
        )
    ''')

    conn.commit()
    conn.close()
    return jsonify({'status': 'ok', 'trades_synced': len(trades)})


@app.route('/api/sync-log', methods=['POST'])
def api_sync_log():
    """Log sync operations for monitoring."""
    data = request.json
    conn = get_db()
    c = conn.cursor()

    c.execute('''
        INSERT INTO sync_log (sync_type, status, records_synced)
        VALUES (?, ?, ?)
    ''', (
        data.get('type', ''),
        data.get('status', ''),
        data.get('records', 0)
    ))

    # Auto-cleanup logs older than 14 days
    cutoff = (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d')
    c.execute('DELETE FROM sync_log WHERE synced_at < ?', (cutoff,))

    conn.commit()
    conn.close()
    return jsonify({'status': 'ok'})


# ── Health Check ────────────────────────────────────────────────────────────

@app.route('/health')
def health():
    """Health check endpoint."""
    return jsonify({'status': 'ok', 'time': datetime.now().isoformat()})


# ── Init & Run ──────────────────────────────────────────────────────────────

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=False)
