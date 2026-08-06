import subprocess
import time
import os
from apscheduler.schedulers.background import BackgroundScheduler
from core.database import sync_market_data_from_taicai

PYTHON_CMD = "/Users/hank/Project/LineStockAgent/line_taicai/venv/bin/python3"
TAICAI_DIR = "/Users/hank/Project/LineStockAgent/line_taicai"

scheduler = BackgroundScheduler()

def scheduled_update():
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Starting scheduled market data update...", flush=True)
    try:
        # 1. Fetch missing targets
        print("Fetching missing targets...", flush=True)
        subprocess.run(
            [PYTHON_CMD, "core/fetch_targets.py", "--missing"],
            cwd=TAICAI_DIR,
            check=True,
            timeout=600
        )
        
        # 2. Run taicai_manager to fetch latest data and write to latest_data.json
        print("Running taicai_manager.py...", flush=True)
        subprocess.run(
            [PYTHON_CMD, "core/taicai_manager.py"],
            cwd=TAICAI_DIR,
            check=True,
            timeout=1200
        )
        
        # 3. Sync to line_taicai SQLite database
        print("Syncing market data to SQLite...", flush=True)
        sync_market_data_from_taicai()
        
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Scheduled update completed successfully.", flush=True)
    except Exception as e:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Scheduled update failed: {e}", flush=True)

def scheduled_notification():
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Starting scheduled notification...", flush=True)
    try:
        from core import notifier
        notifier.check_and_notify_all_users()
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Scheduled notification completed successfully.", flush=True)
    except Exception as e:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Scheduled notification failed: {e}", flush=True)

def scheduled_weekend_update():
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Starting scheduled weekend ALL targets update...", flush=True)
    try:
        # 1. Fetch ALL targets
        print("Fetching ALL targets...", flush=True)
        subprocess.run(
            [PYTHON_CMD, "core/fetch_targets.py", "--all"],
            cwd=TAICAI_DIR,
            check=True
        )
        
        # 2. Run taicai_manager to fetch latest data and write to latest_data.json
        print("Running taicai_manager.py...", flush=True)
        subprocess.run(
            [PYTHON_CMD, "core/taicai_manager.py"],
            cwd=TAICAI_DIR,
            check=True
        )
        
        # 3. Sync to line_taicai SQLite database
        print("Syncing market data to SQLite...", flush=True)
        sync_market_data_from_taicai()
        
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Weekend update completed successfully.", flush=True)
    except Exception as e:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Weekend update failed: {e}", flush=True)

def scheduled_market_trend_update():
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Starting scheduled market trend AI update...", flush=True)
    try:
        subprocess.run(
            [PYTHON_CMD, "core/update_market_cache.py"],
            cwd=TAICAI_DIR,
            check=True
        )
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Market trend AI update completed successfully.", flush=True)
    except Exception as e:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Market trend AI update failed: {e}", flush=True)

def start_scheduler():
    # Schedule to run every 10 minutes between 09:00 and 15:00 on Mon-Fri
    scheduler.add_job(
        scheduled_update, 
        'cron', 
        day_of_week='mon-fri', 
        hour='9-15', 
        minute='*/10',
        id='line_taicai_updater'
    )
    
    # Schedule to notify every 30 minutes from 09:00 to 15:00 on Mon-Fri
    scheduler.add_job(
        scheduled_notification,
        'cron',
        day_of_week='mon-fri',
        hour='9-15',
        minute='0,30',
        id='line_taicai_notifier'
    )
    
    # Schedule to run every Saturday at 10:00 AM to fetch all targets
    scheduler.add_job(
        scheduled_weekend_update,
        'cron',
        day_of_week='sat',
        hour='10',
        minute='0',
        id='line_taicai_weekend_targets_updater'
    )
    
    # Schedule market trend AI report to run once a day after market closes and data is synced
    scheduler.add_job(
        scheduled_market_trend_update,
        'cron',
        day_of_week='mon-fri',
        hour='15',
        minute='30',
        id='line_taicai_market_trend_updater'
    )
    
    scheduler.start()
    print("Scheduler started. Jobs configured:", scheduler.get_jobs(), flush=True)

def stop_scheduler():
    scheduler.shutdown()
    print("Scheduler stopped.", flush=True)
