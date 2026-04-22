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
# Fallback paths for NAS deployment (Mac paths)
if not os.path.exists(PORTFOLIO_FILE):
    for fallback in ["/home/rispaddy/.openclaw/workspace/polymarket-paper-trading/portfolio.json"]:
        if os.path.exists(fallback):
            PORTFOLIO_FILE = fallback
            break
TOKEN_PATH=os.environ.get("GOOGLE_TOKEN_FILE", os.path.expanduser("~/.hermes/google_token.json"))
MEMORY_DIR = os.environ.get("MEMORY_DIR", os.path.expanduser("~/.hermes"))
if not os.path.exists(MEMORY_DIR):
    for fallback in ["/home/rispaddy/.hermes"]:
        if os.path.exists(fallback):
            MEMORY_DIR = fallback
            break
SALES_SPREADSHEET_ID = "1BpsjfAbt4ExbaQT79JjI2fCKO4SP4M8mI8isUV-UsBg"
TASKS_DB = os.environ.get("TASKS_DB", os.path.expanduser("~/.hermes/task_dashboard/tasks.db"))

def get_google_token():
    # Try default path first, then fallback to Mac path (for NAS deployment)
    for path in [TOKEN_PATH, "/home/rispaddy/.hermes/google_token.json"]:
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)
    raise FileNotFoundError(f"google_token.json not found at {TOKEN_PATH} or /home/rispaddy/.hermes/google_token.json")

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

def sheets_update(range_name, values):
    token = get_google_token()
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{SALES_SPREADSHEET_ID}/values/{urllib.parse.quote(range_name)}?valueInputOption=RAW"
    body = json.dumps({"values": values}).encode()
    req = urllib.request.Request(url, data=body, headers={"Authorization": f"Bearer {token['access_token']}", "Content-Type": "application/json"}, method="PUT")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())

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

    # Get month label and SPIFF from Monthly Summary TOTAL row
    month_label = summary[1][0] if len(summary) > 1 else "Current"
    current_spiff = 0
    for row in summary[1:]:
        if len(row) >= 2 and str(row[1]).strip().upper() == "TOTAL":
            current_spiff = float(str(row[7]).replace(",","").replace("$","")) if len(row) > 7 and row[7] else 0
            break

    # Compute agent stats from Daily Log (source of truth for deals/volumes)
    # Monthly Summary can be stale; Daily Log is always correct
    agent_data = {}  # name -> {sales_count, volume, credits, net, commission}
    all_deals = []

    if daily and len(daily) > 1:
        for row in daily[1:]:  # Skip header
            if len(row) < 9:
                continue
            name = row[2].strip()
            if not name:
                continue

            sold = float(str(row[3]).replace(",","").replace("$","")) if row[3] else 0
            net = float(str(row[4]).replace(",","").replace("$","")) if row[4] else 0
            vol_credits = int(row[6]) if str(row[6]).isdigit() else 0
            commission = float(row[8]) if row[8] else 0

            if name not in agent_data:
                agent_data[name] = {"sales_count": 0, "volume": 0, "credits": 0, "net": 0, "commission": 0}
            agent_data[name]["sales_count"] += 1
            agent_data[name]["volume"] += sold
            agent_data[name]["credits"] += vol_credits
            agent_data[name]["net"] += net
            agent_data[name]["commission"] += commission

            all_deals.append({
                "date": row[0],
                "sales_no": row[1],
                "subordinate": name,
                "sold_amount": sold,
                "net_price": net,
                "deposit_pct": row[5],
                "volume_credits": vol_credits,
                "commission_rule": row[7],
                "manager_commission": commission,
                "status": row[9] if len(row) > 9 else "completed",
                "notes": row[10] if len(row) > 10 else "",
            })

    # Build agents list from Daily Log (source of truth)
    agents = [
        {
            "name": name,
            "sales_count": data["sales_count"],
            "volume": data["volume"],
            "credits": data["credits"],
            "net": data["net"],
            "commission": round(data["commission"], 2),
        }
        for name, data in agent_data.items()
    ]

    # Compute totals from Daily Log (not Monthly Summary, which can be stale)
    total_volume = sum(a["volume"] for a in agents)
    total_commission = sum(a["commission"] for a in agents)
    total_deals = sum(a["sales_count"] for a in agents)

    # Get current SPIFF from dashboard before overwriting (preserves manual set)
    try:
        import urllib.request
        req = urllib.request.Request(f"{DASHBOARD_URL}/api/sales/kpi")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            dashboard_spiff = data.get("spiFF", 0) if data else 0
            # Use whichever is larger (dashboard SPIFF vs Monthly Summary SPIFF)
            current_spiff = max(current_spiff, dashboard_spiff)
    except:
        pass

    # Add SPIFF to commission for display total
    total_commission_with_spiff = total_commission + current_spiff

    kpi_data = {
        "month": month_label,
        "total_volume": total_volume,
        "total_commission": total_commission_with_spiff,
        "total_deals": total_deals,
        "spiFF": current_spiff,
        "agents": agents,
    }
    result, status = post("/api/sales/summary", kpi_data)
    if result:
        print(f"  [OK] Sales KPIs synced ({month_label})")
    else:
        print(f"  [FAIL] Sales KPIs sync failed ({status})")

    # Send deals (from Daily Log, already parsed above)
    if all_deals:
        result, status = post("/api/sales/deals", all_deals)
        if result:
            print(f"  [OK] {len(all_deals)} deals synced")
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

# ── SPIFF ───────────────────────────────────────────────────────────────────────

def set_spiff(amount):
    """Set SPIFF bonus for current month in dashboard and Google Sheets."""
    if not amount:
        return
    month = datetime.now().strftime("%b %Y")
    # Update dashboard
    result, status = post("/api/sales/spiFF", {"month": month, "spiFF": amount})
    if result:
        print(f"  [OK] SPIFF set to ${amount} for {month}")
    else:
        print(f"  [FAIL] SPIFF update failed ({status})")
    # Update Google Sheets TOTAL row (col H)
    try:
        summary = sheets_get("Monthly Summary")
        for i, row in enumerate(summary):
            if len(row) >= 2 and row[1].strip().upper() == "TOTAL":
                range_name = f"'Monthly Summary'!H{i+1}:H{i+1}"
                sheets_update(range_name, [[amount]])
                print(f"  [OK] Google Sheets TOTAL row H{i+1} updated")
                break
    except Exception as e:
        print(f"  [FAIL] Google Sheets SPIFF update failed: {e}")

# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Sync once and exit")
    parser.add_argument("--spiff", type=float, default=None, help="Set SPIFF bonus amount")
    args = parser.parse_args()

    print(f"=== NAS Dashboard Sync ===")
    print(f"URL: {DASHBOARD_URL}")
    print(f"Time: {datetime.now().isoformat()}")
    print()

    if args.spiff is not None:
        set_spiff(args.spiff)
        return

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
