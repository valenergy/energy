from app.login_helper import refresh_tokens, decrypt_token
from app.models import Plant, Company, Energy, db
import requests
import os
from datetime import datetime, timedelta
import pandas as pd

def fetch_yield_data(date_str, plant_id):
    ACCESS_KEY = os.environ.get("ACCESS_KEY")
    APP_KEY = os.environ.get("APP_KEY")
    LANG = "_en_US"
    POINTS = "p83072,p83022"

    date_obj = datetime.strptime(date_str, "%Y-%m-%d")

    # Only fetch the plant with the given plant_id
    plant = Plant.query.filter_by(id=plant_id).first()
    if not plant or not plant.plant_id:
        return

    company = Company.query.get(plant.company_id)
    if not company:
        return

    # Refresh tokens if expired
    if not company.access_token or (company.access_token_expires_at and company.access_token_expires_at < datetime.utcnow()):
        refresh_result = refresh_tokens(company.id)
        if "error" in refresh_result:
            return

    access_token = decrypt_token(company.access_token)
    ps_id = str(plant.plant_id)

    # 96 intervals of 15 minutes (24 hours * 4), 12 intervals per 3 hours
    for i in range(0, 24 * 4, 12):
        start_hour = (i // 4)
        start_minute = (i % 4) * 15
        start_time_stamp = f"{date_obj.strftime('%Y%m%d')}{str(start_hour).zfill(2)}{str(start_minute).zfill(2)}00"
        end_index = i + 12
        end_hour = (end_index // 4)
        end_minute = (end_index % 4) * 15
        if end_index == 96:
            end_time_stamp = f"{date_obj.strftime('%Y%m%d')}235900"
        else:
            end_time_stamp = f"{date_obj.strftime('%Y%m%d')}{str(end_hour).zfill(2)}{str(end_minute).zfill(2)}00"
        body = {
            "appkey": APP_KEY,
            "lang": LANG,
            "is_get_point_dict": "1",
            "start_time_stamp": start_time_stamp,
            "end_time_stamp": end_time_stamp,
            "minute_interval": "15",
            "points": POINTS,
            "ps_id_list": [ps_id]
        }
        headers = {
            'authorization': f'Bearer {access_token}',
            'content-type': 'application/json',
            'x-access-key': ACCESS_KEY
        }
        resp = requests.post(
            'https://gateway.isolarcloud.eu/openapi/platform/getPowerStationPointMinuteDataList',
            headers=headers,
            json=body
        )
        if not resp.ok:
            continue
        result_data = resp.json().get("result_data", {})
        plant_data = result_data.get(ps_id)
        if not plant_data or len(plant_data) < 2:
            continue
        key = "p83072" if "p83072" in plant_data[0] else "p83022"
        for j in range(1, len(plant_data)):
            start = float(plant_data[j-1].get(key, 0))
            end = float(plant_data[j].get(key, 0))
            yield_value = end - start
            yield_kwh = round(yield_value / 1000, 2)  # convert Wh to kWh
            ts = plant_data[j]["time_stamp"]
            dt = pd.to_datetime(ts, format="%Y%m%d%H%M%S")
            energy = Energy.query.filter_by(
                date=dt.date(),
                start_period=(dt - timedelta(minutes=15)).time(),
                plant_id=plant.id
            ).first()
            if energy:
                energy.yield_power = yield_kwh
            else:
                energy = Energy(
                    date=dt.date(),
                    start_period=(dt - timedelta(minutes=15)).time(),
                    end_period=dt.time(),
                    duration_in_minutes=15,
                    trader_forecast=None,
                    producer_forecast=None,
                    yield_power=yield_kwh,
                    exported=None,
                    plant_id=plant.id,
                    price=None
                )
                db.session.add(energy)
    db.session.commit()