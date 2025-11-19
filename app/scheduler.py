from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
from db.database import SessionLocal
from app.services.ups_events import aggregate_to_history
from model.model import UPSDevice

def run_hourly_aggregation():
    with SessionLocal() as session:
        devices = session.query(UPSDevice).all()
        # รวมข้อมูลของเมื่อวาน (เพราะวันนี้ยังไม่จบ)
        yesterday = datetime.now() - timedelta(days=1)
        for dev in devices:
            try:
                aggregate_to_history(session, yesterday, dev.id)
            except Exception as e:
                print(f"[AGGREGATE] error for {dev.id}: {e}")
        session.commit()

def start_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(run_hourly_aggregation, "cron", minute=0)
    scheduler.start()
    print("✅ Scheduler started: aggregate UPS history every hour")