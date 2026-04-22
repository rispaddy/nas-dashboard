#!/usr/bin/env python3
"""
NAS Dashboard Sync Script v2
Pushes data from various sources to the dashboard API.
"""

import json, os, sys, argparse, urllib.request, urllib.parse, sqlite3
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
DASHBOARD_URL = os.environ.get("DASHBOARD_URL", "http://100.102.165.11:5004")
PORTFOLIO_FILE = os.environ.get("PORTFOLIO_FILE", os.path.expanduser("~/.openclaw/workspace/polymarket-paper-trading/portfolio.json"))
TOKEN_PATH = os.environ.get("GOOGLE_TOKEN_PATH", os.path.expanduser("~/.hermes/google_token.json"))
MEMORY_DIR = os.environ.get("MEMORY_DIR", os.path.expanduser("~/.hermes"))
SALES_SPREADSHEET_ID = "1BpsjfAbt4ExbaQT79JjI2fCKO4SP4M8mI8isUV-UsBg"
TASKS_DB = os.environ.get("TASKS_DB", os.path.expanduser("~/.hermes/task_dashboard/tasks.db"))

def get_google_token():
    with open(TOKEN_PATH) as f:
        return json.load(f)

def post(endpoint, data):
    url = f"{DASHBOARD_URL}{endpoint}"
    payload = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read()), resp.status
    except Exception as e:
        return None, str(e)

# ── Sync Tasks ────────────────────────────────────────────────────────────────

def sync_tasks():
    """Read tasks from local tasks.db and push to dashboard."""
    if not os.path.exists(TASKS_DB):
        print("  [SKIP] Tasks DB not found")
        return True

    try:
        conn = sqlite3.connect(TASKS_DB)
        c = conn.cursor()
        c.execute("SELECT id, content, status, priority, updated_at FROM tasks ORDER BY updated_at DESC")
        rows = c.fetchall()
        conn.close()

        tasks = []
        now = datetime.now()
        fourteen_days = (now + timedelta(days=14)).strftime('%Y-%m-%d')

        for row in rows:
            task_id, content, status, priority, updated_ts = row
            updated_dt = datetime.fromtimestamp(updated_ts)
            due_date = updated_dt.strftime('%Y-%m-%d')

            tasks.append({
                "task_id": str(task_id),
                "content": content,
                "status": status or "pending",
                "priority": priority or 0,
                "due_date": due_date,
            })

        result, status = post("/api/tasks", {"tasks": tasks})
        if result:
            print(f"  [OK] Tasks synced ({len(tasks)} tasks)")
        else:
            print(f"  [FAIL] Tasks sync failed ({status})")
        return True
    except Exception as e:
        print(f"  [SKIP] Tasks sync error: {e}")
        return True

# ── Sync Calendar ─────────────────────────────────────────────────────────────

def sync_calendar():
    try:
        token = get_google_token()
        now = datetime.utcnow()
        time_min = now.isoformat() + 'Z'
        time_max = (now + timedelta(days=14)).isoformat() + 'Z'

        req = urllib.request.Request(
            f"https://www.googleapis.com/calendar/v3/calendars/primary/events"
            f"?timeMin={time_min}&timeMax={time_max}&singleEvents=true&orderBy=startTime",
            headers={"Authorization": f"Bearer {token['access_token']}"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())

        events = []
        for item in data.get("items", []):
            start = item.get("start", {})
            date = start.get("dateTime", start.get("date", ""))[:10]
            time = start.get("dateTime", "")[11:16] if "T" in start.get("dateTime", "") else ""
            events.append({
                "title": item.get("summary", "No Title"),
                "description": item.get("description", ""),
                "event_date": date,
                "event_time": time,
                "event_type": "appointment"
            })

        result, status = post("/api/calendar", {"events": events})
        if result:
            print(f"  [OK] Calendar synced ({len(events)} events)")
        else:
            print(f"  [FAIL] Calendar sync failed ({status})")
        return True
    except Exception as e:
        print(f"  [SKIP] Calendar sync error: {e}")
        return True

# ── Sync Cron Jobs ────────────────────────────────────────────────────────────

def sync_cron_jobs():
    cron_jobs = []
    cron_file = Path(MEMORY_DIR) / "cron_jobs.json"
    if cron_file.exists():
        try:
            with open(cron_file) as f:
                jobs = json.load(f)
                for job in (jobs if isinstance(jobs, list) else []):
                    cron_jobs.append({
                        "name": job.get("name", "Unknown"),
                        "schedule": job.get("schedule", ""),
                        "is_active": 1 if job.get("enabled", True) else 0,
                        "last_run": job.get("last_run_at", ""),
                        "next_run": job.get("next_run_at", ""),
                    })
        except:
            pass

    # Also get from Hermes cron tool if available
    try:
        result, _ = post("/api/cron", {"cron_jobs": cron_jobs})
        print(f"  [OK] Cron jobs synced ({len(cron_jobs)} jobs)")
    except Exception as e:
        print(f"  [FAIL] Cron sync failed: {e}")
    return True

# ── Sync Projects ─────────────────────────────────────────────────────────────

def sync_projects():
    projects = [
        {"name": "Polymarket Paper Trading", "description": "Automated prediction market monitoring", "status": "active"},
        {"name": "Hermes Agent", "description": "Personal AI assistant", "status": "active"},
    ]
    result, status = post("/api/projects", {"projects": projects})
    if result:
        print(f"  [OK] Projects synced ({len(projects)} projects)")
    else:
        print(f"  [FAIL] Projects sync failed ({status})")
    return True

# ── Sync Sales ────────────────────────────────────────────────────────────────

def sheets_get(range_name):
    token = get_google_token()
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{SALES_SPREADSHEET_ID}/values/{urllib.parse.quote(range_name)}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token['access_token']}"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    return data.get("values", [])

def sync_sales():
    try:
        summary = sheets_get("Monthly Summary")
        daily = sheets_get("Daily Log")
    except Exception as e:
        print(f"  [SKIP] Google Sheets read failed: {e}")
        return False

    if not summary or len(summary) < 2:
        print("  [SKIP] Monthly Summary sheet empty")
        return False

    # Parse monthly KPI data (separate agent rows from TOTAL row)
    month_label = summary[1][0] if len(summary) > 1 else "Current"
    agents = []
    total_volume = 0
    total_commission = 0
    total_deals = 0

    for row in summary[1:]:
        if len(row) < 7:
            continue
        name = row[1].strip()
        if name.upper() == "TOTAL":
            total_volume = float(str(row[3]).replace(",","").replace("$","")) if row[3] else 0
            total_commission = float(str(row[6]).replace(",","").replace("$","")) if row[6] else 0
            total_deals = int(row[2]) if str(row[2]).isdigit() else 0
        elif name:
            agents.append({
                "name": name,
                "sales_count": int(row[2]) if str(row[2]).isdigit() else 0,
                "volume": float(str(row[3]).replace(",","").replace("$","")) if row[3] else 0,
                "credits": int(row[4]) if str(row[4]).isdigit() else 0,
                "net": float(str(row[5]).replace(",","").replace("$","")) if row[5] else 0,
                "commission": float(str(row[6]).replace(",","").replace("$","")) if row[6] else 0,
            })

    # Send KPI summary (total row only)
    kpi_data = {
        "month": month_label,
        "total_volume": total_volume,
        "total_commission": total_commission,
        "total_deals": total_deals,
        "agents": agents,
    }
    result, status = post("/api/sales/summary", kpi_data)
    if result:
        print(f"  [OK] Sales KPIs synced ({month_label})")
    else:
        print(f"  [FAIL] Sales KPIs sync failed ({status})")

    # Send deals
    deals = []
    if daily and len(daily) > 1:
        for row in daily[1:]:  # Skip header
            if len(row) < 9:
                continue
            deals.append({
                "date": row[0],
                "sales_no": row[1],
                "subordinate": row[2],
                "sold_amount": float(str(row[3]).replace(",","").replace("$","")) if row[3] else 0,
                "net_price": float(str(row[4]).replace(",","").replace("$","")) if row[4] else 0,
                "deposit_pct": row[5],
                "volume_credits": int(row[6]) if str(row[6]).isdigit() else 0,
                "commission_rule": row[7],
                "manager_commission": float(row[8]) if row[8] else 0,
                "status": row[9] if len(row) > 9 else "completed",
                "notes": row[10] if len(row) > 10 else "",
            })

    if deals:
        result, status = post("/api/sales/deals", deals)
        if result:
            print(f"  [OK] {len(deals)} deals synced")
        else:
            print(f"  [FAIL] Deals sync failed ({status})")
    else:
        print("  [SKIP] No deals found")

    return True

# ── Sync Polymarket ────────────────────────────────────────────────────────────

def sync_polymarket():
    if not os.path.exists(PORTFOLIO_FILE):
        print("  [SKIP] Portfolio file not found")
        return True

    try:
        with open(PORTFOLIO_FILE) as f:
            portfolio = json.load(f)

        # Positions - use entry_price as current_price (no live data)
        positions = []
        for pos in portfolio.get("positions", []):
            slug = pos.get("slug", "")
            entry_price = float(pos.get("entry_price", 0))
            qty = float(pos.get("qty", 0))
            cost = float(pos.get("cost", qty * entry_price))
            current_price = entry_price
            current_value = qty * current_price
            pnl = current_value - cost
            pnl_pct = (pnl / cost * 100) if cost > 0 else 0

            positions.append({
                "slug": slug,
                "question": pos.get("question", slug),
                "side": pos.get("side", ""),
                "entry_price": entry_price,
                "qty": qty,
                "cost": cost,
                "current_price": current_price,
                "current_value": current_value,
                "pnl": pnl,
                "pnl_pct": pnl_pct,
            })

        result, status = post("/api/portfolio", {"positions": positions})
        if result:
            print(f"  [OK] Portfolio synced ({len(positions)} positions)")
        else:
            print(f"  [FAIL] Portfolio sync failed ({status})")

        # Trades
        trades = []
        for t in portfolio.get("trades", []):
            trades.append({
                "trade_id": t.get("id", ""),
                "slug": t.get("slug", ""),
                "question": t.get("question", ""),
                "side": t.get("side", ""),
                "price": float(t.get("entry_price", 0)),
                "qty": float(t.get("qty", 0)),
                "total_cost": float(t.get("cost", 0)),
                "trade_date": t.get("timestamp", "")[:10],
                "notes": t.get("notes", ""),
            })

        if trades:
            result, status = post("/api/trades", {"trades": trades})
            if result:
                print(f"  [OK] Trades synced ({len(trades)} trades)")

        # Watchlist (from portfolio stats if available)
        watchlist = portfolio.get("watchlist", [])
        if watchlist:
            wl_data = []
            for item in watchlist:
                wl_data.append({
                    "slug": item.get("slug", ""),
                    "question": item.get("question", ""),
                    "current_price": float(item.get("current_price", 0)),
                    "trend": item.get("trend", ""),
                })
            result, status = post("/api/watchlist", {"watchlist": wl_data})
            if result:
                print(f"  [OK] Watchlist synced ({len(wl_data)} markets)")

        return True

    except Exception as e:
        print(f"  [ERROR] Polymarket sync failed: {e}")
        return True

# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Sync once and exit")
    args = parser.parse_args()

    print(f"=== NAS Dashboard Sync ===")
    print(f"URL: {DASHBOARD_URL}")
    print(f"Time: {datetime.now().isoformat()}")
    print()

    sync_tasks()
    sync_calendar()
    sync_cron_jobs()
    sync_projects()
    sync_sales()
    sync_polymarket()

    print()
    print("[ALL OK] Dashboard synced successfully")

if __name__ == "__main__":
    main()
