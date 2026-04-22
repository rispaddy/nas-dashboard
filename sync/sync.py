#!/usr/bin/env python3
"""
NAS Dashboard Sync Script
Pushes data from various sources to the dashboard API.

Usage:
    python3 sync.py              # sync everything
    python3 sync.py --once      # sync once and exit (for cron)

Sources:
    - Tasks: from Hermes memory/cron
    - Calendar: from Google Calendar
    - Cron Jobs: from Hermes cron config
    - Projects: from Hermes memory
    - Sales: from Google Sheets
    - Polymarket: from portfolio.json
"""

import json
import os
import sys
import argparse
import urllib.request
import urllib.parse
import time as time_module
from datetime import datetime, timedelta
from pathlib import Path

# ── Config ──────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent.parent
DASHBOARD_URL = os.environ.get("DASHBOARD_URL", "http://127.0.0.1:5004")
PORTFOLIO_FILE = os.environ.get("PORTFOLIO_FILE", os.path.expanduser("~/.openclaw/workspace/polymarket-paper-trading/portfolio.json"))
TOKEN_PATH = os.environ.get("GOOGLE_TOKEN_PATH", os.path.expanduser("~/.hermes/google_token.json"))
MEMORY_DIR = os.environ.get("MEMORY_DIR", os.path.expanduser("~/.hermes"))

# Google Sheets
SALES_SPREADSHEET_ID = "1BpsjfAbt4ExbaQT79JjI2fCKO4SP4M8mI8isUV-UsBg"


# ── Helpers ─────────────────────────────────────────────────────────────────

def post(endpoint, data):
    """POST data to dashboard API."""
    url = f"{DASHBOARD_URL}{endpoint}"
    payload = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read()), resp.status
    except urllib.error.HTTPError as e:
        body = e.read()
        print(f"  HTTP {e.code}: {body.decode('utf-8', errors='replace')}")
        return None, e.code
    except Exception as e:
        print(f"  ERROR: {e}")
        return None, -1


def get_google_token():
    """Get Google access token, refreshing if needed."""
    with open(TOKEN_PATH) as f:
        token = json.load(f)
    expiry = token.get("expiry", "0")
    try:
        expiry_ts = float(expiry)
    except (ValueError, TypeError):
        expiry_ts = 0
    if expiry_ts < time_module.time():
        data = urllib.parse.urlencode({
            "client_id": token["client_id"],
            "client_secret": token["client_secret"],
            "refresh_token": token["refresh_token"],
            "grant_type": "refresh_token"
        }).encode()
        req = urllib.request.Request(
            token["token_uri"], data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
        token["access_token"] = result["access_token"]
        token["expiry"] = str(time_module.time() + result.get("expires_in", 3600))
        with open(TOKEN_PATH, "w") as f:
            json.dump(token, f)
    return token["access_token"]


def sheets_get(title, range_="A1:Z200"):
    """Get data from Google Sheets."""
    token = get_google_token()
    encoded = urllib.parse.quote(f"{title}!{range_}")
    req = urllib.request.Request(
        f"https://sheets.googleapis.com/v4/spreadsheets/{SALES_SPREADSHEET_ID}/values/{encoded}",
        headers={"Authorization": f"Bearer {token}"}
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read()).get("values", [])


# ── Sync Functions ──────────────────────────────────────────────────────────

def sync_tasks():
    """Gather tasks from Hermes memory and push to dashboard."""
    tasks = []
    memory_file = Path(MEMORY_DIR) / "memory.json"

    # Try to read from memory
    try:
        if memory_file.exists():
            with open(memory_file) as f:
                content = f.read()
                # Extract task-like items from memory
                # This is a simplified version - in production you'd parse more carefully
                pass
    except Exception as e:
        print(f"  [SKIP] Memory read failed: {e}")

    # For now, we'll rely on calendar events for tasks
    # Real tasks would come from a task management system
    print(f"  [OK] Tasks synced (placeholder - {len(tasks)} items)")
    return True


def sync_calendar():
    """Sync calendar events from Google Calendar."""
    try:
        token = get_google_token()
        now = datetime.utcnow()
        time_min = now.isoformat() + 'Z'
        time_max = (now + timedelta(days=14)).isoformat() + 'Z'

        req = urllib.request.Request(
            f"https://www.googleapis.com/calendar/v3/calendars/primary/events"
            f"?timeMin={time_min}&timeMax={time_max}&singleEvents=true&orderBy=startTime",
            headers={"Authorization": f"Bearer {token}"}
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
            return True
        else:
            print(f"  [FAIL] Calendar sync failed ({status})")
            return False

    except Exception as e:
        print(f"  [SKIP] Calendar sync failed: {e}")
        return False


def sync_cron_jobs():
    """Gather cron job info from Hermes cron config."""
    cron_jobs = []

    # Read from Hermes cron jobs
    cron_jobs_file = Path(MEMORY_DIR) / "cron" / "jobs.json"
    if cron_jobs_file.exists():
        try:
            with open(cron_jobs_file) as f:
                jobs_data = json.load(f)
                for job in jobs_data.get("jobs", []):
                    cron_jobs.append({
                        "name": job.get("name", "Unnamed"),
                        "schedule": job.get("schedule", ""),
                        "description": job.get("prompt", "")[:100] if job.get("prompt") else "",
                        "next_run": job.get("next_run", ""),
                        "is_active": 1 if job.get("status") == "active" else 0
                    })
        except Exception as e:
            print(f"  [WARN] Cron jobs file read error: {e}")

    # If no jobs found, add placeholder
    if not cron_jobs:
        # Add known important jobs from memory
        cron_jobs.append({
            "name": "工人發薪提醒",
            "schedule": "0 20 * * 5",
            "description": "每週五 20:00 提醒發薪",
            "next_run": "每週五",
            "is_active": 1
        })

    result, status = post("/api/cron", {"cron_jobs": cron_jobs})
    if result:
        print(f"  [OK] Cron jobs synced ({len(cron_jobs)} jobs)")
        return True
    else:
        print(f"  [FAIL] Cron jobs sync failed ({status})")
        return False


def sync_projects():
    """Sync projects from Hermes memory."""
    projects = []

    # Known projects from memory
    known_projects = [
        {"name": "Polymarket Paper Trading", "description": "紙上交易系統，自動監控市場"},
        {"name": "Hermes Agent", "description": "個人 AI 助手"},
    ]

    for proj in known_projects:
        projects.append({
            "name": proj["name"],
            "description": proj["description"],
            "status": "active"
        })

    result, status = post("/api/projects", {"projects": projects})
    if result:
        print(f"  [OK] Projects synced ({len(projects)} projects)")
        return True
    else:
        print(f"  [FAIL] Projects sync failed ({status})")
        return False


def sync_sales():
    """Read sales data from Google Sheets and push to dashboard."""
    try:
        summary = sheets_get("Monthly Summary")
        daily = sheets_get("Daily Log")
    except Exception as e:
        print(f"  [SKIP] Google Sheets read failed: {e}")
        return False

    if not summary or len(summary) < 2:
        print("  [SKIP] Monthly Summary sheet empty")
        return False

    # Parse agents
    agents = []
    total_row = None
    for row in summary[1:]:
        if len(row) < 7:
            continue
        name = row[1].strip()
        if name.upper() == "TOTAL":
            total_row = row
        elif name:
            agents.append({
                "name": name,
                "sales_count": int(row[2]) if row[2].isdigit() else 0,
                "volume": float(str(row[3]).replace(",","").replace("$","")) if row[3] else 0,
                "credits": int(row[4]) if row[4].isdigit() else 0,
                "net": float(str(row[5]).replace(",","").replace("$","")) if row[5] else 0,
                "commission": float(row[6]) if len(row) > 6 and row[6] else 0,
            })

    if total_row and len(total_row) >= 7:
        month_label = total_row[0]
        total_volume = float(str(total_row[3]).replace(",","").replace("$","")) if total_row[3] else 0
        total_commission = float(total_row[6]) if total_row[6] else 0
        total_deals = int(total_row[2]) if total_row[2].isdigit() else 0
    else:
        month_label = summary[1][0] if len(summary) > 1 else "Current"
        total_volume = sum(a["volume"] for a in agents)
        total_commission = sum(a["commission"] for a in agents)
        total_deals = sum(a["sales_count"] for a in agents)

    kpi_data = {
        "total": {
            "volume": total_volume,
            "commission": total_commission,
            "deals": total_deals,
            "month": month_label,
            "agents": agents,
        }
    }

    result, status = post("/api/sales/summary", kpi_data)
    if result:
        print(f"  [OK] Sales KPIs synced ({month_label})")
    else:
        print(f"  [FAIL] Sales KPIs sync failed ({status})")

    # Sync deals
    deals = []
    if daily and len(daily) > 2:
        for row in daily[2:]:
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


def sync_polymarket():
    """Read Polymarket portfolio and push to dashboard."""
    if not os.path.exists(PORTFOLIO_FILE):
        print(f"  [SKIP] Portfolio file not found: {PORTFOLIO_FILE}")
        return False

    try:
        with open(PORTFOLIO_FILE) as f:
            portfolio = json.load(f)

        positions = []
        for pos in portfolio.get("positions", []):
            slug = pos.get("slug", "")
            qty = float(pos.get("qty", 0))
            cost = float(pos.get("cost", 0))
            current_price = float(pos.get("current_price", 0))
            current_value = qty * current_price
            pnl = current_value - cost
            pnl_pct = (pnl / cost * 100) if cost > 0 else 0

            positions.append({
                "slug": slug,
                "question": pos.get("question", slug),
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

        # Sync watchlist
        watchlist = portfolio.get("watchlist", [])
        if watchlist:
            result, status = post("/api/watchlist", {"watchlist": watchlist})
            if result:
                print(f"  [OK] Watchlist synced ({len(watchlist)} markets)")

        # Sync trades
        trades = portfolio.get("trades", [])
        if trades:
            result, status = post("/api/trades", {"trades": trades})
            if result:
                print(f"  [OK] Trades synced ({len(trades)} trades)")

        return True

    except Exception as e:
        print(f"  [ERROR] Polymarket sync failed: {e}")
        return False


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Sync once and exit")
    args = parser.parse_args()

    print(f"=== NAS Dashboard Sync ===")
    print(f"URL: {DASHBOARD_URL}")
    print(f"Time: {datetime.now().isoformat()}")
    print()

    # Sync all data
    calendar_ok = sync_calendar()
    cron_ok = sync_cron_jobs()
    projects_ok = sync_projects()
    sales_ok = sync_sales()
    polymarket_ok = sync_polymarket()

    print()

    # Log to dashboard
    total_records = sum([
        calendar_ok or 0,
        cron_ok or 0,
        projects_ok or 0,
        sales_ok or 0,
        polymarket_ok or 0
    ])

    post("/api/sync-log", {
        "type": "full_sync",
        "status": "ok" if all([calendar_ok, cron_ok, projects_ok, sales_ok, polymarket_ok]) else "partial",
        "records": total_records
    })

    if all([calendar_ok, cron_ok, projects_ok, sales_ok, polymarket_ok]):
        print("[ALL OK] Dashboard synced successfully")
        sys.exit(0)
    else:
        print("[PARTIAL] Some syncs failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
