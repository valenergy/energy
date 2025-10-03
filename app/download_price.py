import requests
import random
from datetime import datetime, timedelta
from app.models import db, Price

def download_save_price(date_str=None):
    """
    Download and save price data for a specific date (default: tomorrow).
    """
    if date_str is None:
        date_str = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    rand = round(random.random(), 16)
    print(f"Downloading prices for {date_str} with rand={rand}")
    url = f"https://ibex.bg/Ext/SDAC_PROD/DAM_Page/api.php?action=get_data&date={date_str}&lang=bg&rand={rand}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    data = response.json()

    base_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    # Remove existing prices for this date to avoid duplicates
    Price.query.filter_by(date=base_date).delete()
    Price.query.filter_by(date=base_date + timedelta(days=1)).delete()
    db.session.commit()

    for idx, entry in enumerate(data.get("main_data", [])):
        delivery_period = entry.get("delivery_period", "")
        if "-" in delivery_period:
            start_time, end_time = delivery_period.split("-")
            # Add +1 hour to both start and end times
            start_dt = datetime.strptime(start_time.strip(), "%H:%M") + timedelta(hours=1)
            end_dt = datetime.strptime(end_time.strip(), "%H:%M") + timedelta(hours=1)
            hour = start_dt.hour
            delivery_period_eet = f"{start_dt.strftime('%H:%M')} - {end_dt.strftime('%H:%M')}"
        else:
            hour = None
            delivery_period_eet = delivery_period

        # For the last 4 entries, store for the next day
        if idx >= 92:  # 0-based index, so 92,93,94,95 are last 4
            price_date = base_date + timedelta(days=1)
        else:
            price_date = base_date

        price = Price(
            date=price_date,
            hour=hour,
            price=float(entry["price"]),
            product=entry.get("product"),
            delivery_period=delivery_period_eet
        )
        db.session.add(price)
    db.session.commit()
    print(f"Downloaded and saved prices for {date_str} (last 4 periods stored for next day)")
