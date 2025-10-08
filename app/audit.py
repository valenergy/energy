from app.models import AuditLog, db
from datetime import datetime
from zoneinfo import ZoneInfo

def log_audit(principal, message):
    entry = AuditLog(
        ts = datetime.now(ZoneInfo("Europe/Sofia")),
        principal=principal,
        message=message
    )
    db.session.add(entry)
    db.session.commit()