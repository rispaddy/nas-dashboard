#!/usr/bin/env python3
"""
NAS Dashboard - Flask App
Summary, Sales, Polymarket pages.
"""

import sqlite3, os
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)
app.template_folder = 'templates'
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get('DATA_DIR', os.path.join(BASE_DIR, 'data'))
DB_PATH = os.environ.get('DB_PATH', os.path.join(DATA_DIR, 'dashboard.db'))

os.makedirs(DATA_DIR, exist_ok=True)

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()

    # Tasks table
    c.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT UNIQUE,
            content TEXT,
            status TEXT DEFAULT 'pending',
            priority INTEGER DEFAULT 0,
            due_date TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Calendar events
    c.execute('''
        CREATE TABLE IF NOT EXISTS calendar_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            description TEXT,
            event_date TEXT,
            event_time TEXT,
            event_type TEXT DEFAULT 'appointment',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Cron jobs
    c.execute('''
        CREATE TABLE IF NOT EXISTS cron_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            schedule TEXT,
            is_active INTEGER DEFAULT 1,
            last_run TEXT,
            next_run TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Projects
    c.execute('''
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            description TEXT,
            status TEXT DEFAULT 'active',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Sales KPIs (one row per month = TOTAL only)
    c.execute('''
        CREATE TABLE IF NOT EXISTS sales_kpis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            month_label TEXT UNIQUE,
            total_volume REAL,
            total_commission REAL,
            total_deals INTEGER,
            spiFF REAL DEFAULT 0,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Sales agent KPIs (one row per agent per month)
    c.execute('''
        CREATE TABLE IF NOT EXISTS sales_agent_kpis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            month_label TEXT,
            agent_name TEXT,
            agent_volume REAL,
            agent_credits INTEGER,
            agent_net REAL,
            agent_commission REAL,
            UNIQUE(month_label, agent_name)
        )
    ''')

    # Sales records (daily log deals)
    c.execute('''
        CREATE TABLE IF NOT EXISTS sales_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            sales_no TEXT,
            subordinate TEXT,
            sold_amount REAL,
            net_price REAL,
            deposit_pct TEXT,
            volume_credits INTEGER,
            commission_rule TEXT,
            manager_commission REAL,
            status TEXT DEFAULT 'completed',
            notes TEXT,
            UNIQUE(sales_no, date)
        )
    ''')

    # Polymarket positions
    c.execute('''
        CREATE TABLE IF NOT EXISTS polymarket_positions (
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
        )
    ''')

    # Polymarket watchlist
    c.execute('''
        CREATE TABLE IF NOT EXISTS polymarket_watchlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            market_slug TEXT UNIQUE,
            market_question TEXT,
            current_price REAL,
            trend TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Polymarket trades
    c.execute('''
        CREATE TABLE IF NOT EXISTS polymarket_trades (
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
        )
    ''')

    # Sync log
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

init_db()

# ── Routes ──────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('summary.html')

@app.route('/summary')
def summary():
    conn = get_db()
    c = conn.cursor()
    today = datetime.now().strftime('%Y-%m-%d')
    two_weeks = (datetime.now() + timedelta(days=14)).strftime('%Y-%m-%d')

    # Upcoming tasks (next 14 days)
    c.execute('''
        SELECT * FROM tasks
        WHERE due_date BETWEEN ? AND ?
        AND status != 'completed'
        ORDER BY due_date ASC, priority DESC
    ''', (today, two_weeks))
    upcoming_tasks = [dict(row) for row in c.fetchall()]

    # Overdue tasks
    c.execute('''
        SELECT * FROM tasks
        WHERE due_date < ? AND status != 'completed'
        ORDER BY due_date ASC
    ''', (today,))
    overdue_tasks = [dict(row) for row in c.fetchall()]

    # Upcoming calendar events
    c.execute('''
        SELECT * FROM calendar_events
        WHERE event_date BETWEEN ? AND ?
        ORDER BY event_date ASC, event_time ASC
    ''', (today, two_weeks))
    upcoming_events = [dict(row) for row in c.fetchall()]

    # Active cron jobs
    c.execute('SELECT * FROM cron_jobs WHERE is_active = 1 ORDER BY name ASC')
    active_crons = [dict(row) for row in c.fetchall()]

    # Active projects
    c.execute('SELECT * FROM projects WHERE status = "active" ORDER BY updated_at DESC')
    active_projects = [dict(row) for row in c.fetchall()]

    # Stats
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
    conn = get_db()
    c = conn.cursor()

    # Get latest KPI (total for most recent month)
    c.execute('SELECT * FROM sales_kpis ORDER BY month_label DESC LIMIT 1')
    row = c.fetchone()
    latest_kpi = dict(row) if row else None

    # Get all KPIs for chart (both total and agent)
    c.execute('SELECT * FROM sales_kpis ORDER BY month_label ASC')
    total_kpis = [dict(row) for row in c.fetchall()]

    c.execute('SELECT * FROM sales_agent_kpis ORDER BY month_label ASC, agent_volume DESC')
    agent_kpis = [dict(row) for row in c.fetchall()]

    # Recent sales (last 14 days)
    two_weeks_ago = (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d')
    c.execute('''
        SELECT * FROM sales_records
        WHERE date >= ?
        ORDER BY date DESC, id DESC
    ''', (two_weeks_ago,))
    recent_sales = [dict(row) for row in c.fetchall()]

    # Agent breakdown (last 14 days)
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
        total_kpis=total_kpis,
        agent_kpis=agent_kpis,
        recent_sales=recent_sales,
        agent_breakdown=agent_breakdown
    )

@app.route('/polymarket')
def polymarket():
    conn = get_db()
    c = conn.cursor()

    # Get open positions
    c.execute('SELECT * FROM polymarket_positions WHERE status = "open" ORDER BY updated_at DESC')
    positions = [dict(row) for row in c.fetchall()]

    # Get watchlist
    c.execute('SELECT * FROM polymarket_watchlist ORDER BY updated_at DESC')
    watchlist = [dict(row) for row in c.fetchall()]

    # Get recent trades
    c.execute('SELECT * FROM polymarket_trades ORDER BY created_at DESC LIMIT 20')
    trades = [dict(row) for row in c.fetchall()]

    # Totals
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

@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'time': datetime.now().isoformat()})

# ── API Endpoints (POST only) ──────────────────────────────────────────────────

@app.route('/api/tasks', methods=['POST'])
def api_tasks():
    data = request.json
    tasks = data.get('tasks', [])
    conn = get_db()
    c = conn.cursor()
    for t in tasks:
        c.execute('''
            INSERT OR REPLACE INTO tasks (task_id, content, status, priority, due_date, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ''', (t.get('task_id', ''), t.get('content', ''), t.get('status', 'pending'),
              t.get('priority', 0), t.get('due_date', '')))
    conn.commit()
    conn.close()
    return jsonify({'status': 'ok', 'tasks_synced': len(tasks)})

@app.route('/api/calendar', methods=['POST'])
def api_calendar():
    data = request.json
    events = data.get('events', [])
    conn = get_db()
    c = conn.cursor()
    c.execute('DELETE FROM calendar_events')
    for e in events:
        c.execute('''
            INSERT INTO calendar_events (title, description, event_date, event_time, event_type)
            VALUES (?, ?, ?, ?, ?)
        ''', (e.get('title', ''), e.get('description', ''), e.get('event_date', ''),
              e.get('event_time', ''), e.get('event_type', 'appointment')))
    conn.commit()
    conn.close()
    return jsonify({'status': 'ok', 'events_synced': len(events)})

@app.route('/api/cron', methods=['POST'])
def api_cron():
    data = request.json
    crons = data.get('cron_jobs', [])
    conn = get_db()
    c = conn.cursor()
    for cron in crons:
        c.execute('''
            INSERT OR REPLACE INTO cron_jobs (name, schedule, is_active, last_run, next_run, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ''', (cron.get('name', ''), cron.get('schedule', ''),
              cron.get('is_active', 1), cron.get('last_run', ''), cron.get('next_run', '')))
    conn.commit()
    conn.close()
    return jsonify({'status': 'ok', 'crons_synced': len(crons)})

@app.route('/api/projects', methods=['POST'])
def api_projects():
    data = request.json
    projects = data.get('projects', [])
    conn = get_db()
    c = conn.cursor()
    for p in projects:
        c.execute('''
            INSERT OR REPLACE INTO projects (name, description, status, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ''', (p.get('name', ''), p.get('description', ''), p.get('status', 'active')))
    conn.commit()
    conn.close()
    return jsonify({'status': 'ok', 'projects_synced': len(projects)})

@app.route('/api/sales/summary', methods=['POST'])
def api_sales_summary():
    data = request.json
    conn = get_db()
    c = conn.cursor()

    month = data.get('month', '')
    total_volume = data.get('total_volume', 0)
    total_commission = data.get('total_commission', 0)
    total_deals = data.get('total_deals', 0)
    spiFF = data.get('spiFF', 0)
    agents = data.get('agents', [])

    # Upsert total KPI
    c.execute('''
        INSERT OR REPLACE INTO sales_kpis (month_label, total_volume, total_commission, total_deals, spiFF, updated_at)
        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    ''', (month, total_volume, total_commission, total_deals, spiFF))

    # Upsert agent KPIs
    for a in agents:
        c.execute('''
            INSERT OR REPLACE INTO sales_agent_kpis
            (month_label, agent_name, agent_volume, agent_credits, agent_net, agent_commission)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (month, a.get('name', ''), a.get('volume', 0), a.get('credits', 0),
              a.get('net', 0), a.get('commission', 0)))

    conn.commit()
    conn.close()
    return jsonify({'status': 'ok'})

@app.route('/api/sales/kpi', methods=['GET'])
def api_sales_kpi():
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM sales_kpis ORDER BY month_label DESC LIMIT 1')
    row = c.fetchone()
    conn.close()
    if row:
        return jsonify(dict(row))
    return jsonify({})

@app.route('/api/sales/spiFF', methods=['POST'])
def api_sales_spiff():
    data = request.json
    conn = get_db()
    c = conn.cursor()
    month = data.get('month', '')
    spiFF = data.get('spiFF', 0)
    c.execute('''
        UPDATE sales_kpis SET spiFF = ?, updated_at = CURRENT_TIMESTAMP
        WHERE month_label = ?
    ''', (spiFF, month))
    conn.commit()
    conn.close()
    return jsonify({'status': 'ok', 'spiFF': spiFF})

@app.route('/api/sales/deals', methods=['POST'])
def api_sales_deals():
    data = request.json
    deals = data if isinstance(data, list) else []
    conn = get_db()
    c = conn.cursor()

    # Delete old deals (last 14 days cutoff)
    cutoff = (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d')
    c.execute('DELETE FROM sales_records WHERE date < ?', (cutoff,))

    # Insert all deals (upsert by sales_no + date)
    for d in deals:
        c.execute('''
            INSERT OR REPLACE INTO sales_records
            (date, sales_no, subordinate, sold_amount, net_price, deposit_pct,
             volume_credits, commission_rule, manager_commission, status, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (d.get('date', ''), d.get('sales_no', ''), d.get('subordinate', ''),
              d.get('sold_amount', 0), d.get('net_price', 0), d.get('deposit_pct', ''),
              d.get('volume_credits', 0), d.get('commission_rule', ''),
              d.get('manager_commission', 0), d.get('status', 'completed'), d.get('notes', '')))

    conn.commit()
    conn.close()
    return jsonify({'status': 'ok', 'deals_synced': len(deals)})

@app.route('/api/portfolio', methods=['POST'])
def api_portfolio():
    data = request.json
    positions = data.get('positions', [])
    conn = get_db()
    c = conn.cursor()
    c.execute('DELETE FROM polymarket_positions')
    for p in positions:
        c.execute('''
            INSERT INTO polymarket_positions
            (market_slug, market_question, side, entry_price, qty, cost,
             current_price, current_value, pnl, pnl_pct, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (p.get('slug', ''), p.get('question', ''), p.get('side', ''),
              p.get('entry_price', 0), p.get('qty', 0), p.get('cost', 0),
              p.get('current_price', 0), p.get('current_value', 0),
              p.get('pnl', 0), p.get('pnl_pct', 0), 'open'))
    conn.commit()
    conn.close()
    return jsonify({'status': 'ok', 'positions_synced': len(positions)})

@app.route('/api/watchlist', methods=['POST'])
def api_watchlist():
    data = request.json
    watchlist = data.get('watchlist', [])
    conn = get_db()
    c = conn.cursor()
    c.execute('DELETE FROM polymarket_watchlist')
    for w in watchlist:
        c.execute('''
            INSERT INTO polymarket_watchlist (market_slug, market_question, current_price, trend)
            VALUES (?, ?, ?, ?)
        ''', (w.get('slug', ''), w.get('question', ''), w.get('current_price', 0), w.get('trend', '')))
    conn.commit()
    conn.close()
    return jsonify({'status': 'ok', 'watchlist_synced': len(watchlist)})

@app.route('/api/trades', methods=['POST'])
def api_trades():
    data = request.json
    trades = data.get('trades', [])
    conn = get_db()
    c = conn.cursor()
    for t in trades:
        c.execute('''
            INSERT OR REPLACE INTO polymarket_trades
            (trade_id, market_slug, market_question, side, price, qty, total_cost, trade_date, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (t.get('trade_id', ''), t.get('slug', ''), t.get('question', ''),
              t.get('side', ''), t.get('price', 0), t.get('qty', 0),
              t.get('total_cost', 0), t.get('trade_date', ''), t.get('notes', '')))
    conn.commit()
    conn.close()
    return jsonify({'status': 'ok', 'trades_synced': len(trades)})

@app.route('/api/sync-log', methods=['POST'])
def api_sync_log():
    data = request.json
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        INSERT INTO sync_log (sync_type, status, records_synced)
        VALUES (?, ?, ?)
    ''', (data.get('type', ''), data.get('status', ''), data.get('count', 0)))
    conn.commit()
    conn.close()
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
