from app.models import AuditLog, db
from datetime import datetime
from zoneinfo import ZoneInfo

def log_audit(principal, message):
    # Ensure principal is a simple string before saving
    if not isinstance(principal, str):
        principal = getattr(principal, "email", None) or getattr(principal, "id", None) or str(principal)
    entry = AuditLog(
        ts = datetime.now(ZoneInfo("Europe/Sofia")),
        principal = principal,
        message = message
    )
    db.session.add(entry)
    db.session.commit()