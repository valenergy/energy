import requests
import os
from app.login_helper import get_valid_access_token
from app.models import Invertor
from datetime import datetime
from flask_security import current_user

def get_plants_current_power(plant_ids):
    ACCESS_KEY = os.environ.get("ACCESS_KEY")
    APP_KEY = os.environ.get("APP_KEY")

    access_token = get_valid_access_token(current_user.company_id)

    url = "https://gateway.isolarcloud.eu/openapi/platform/getPowerStationRealTimeData"
    headers = {
        "authorization": f"Bearer {access_token}",
        "content-type": "application/json",
        "x-access-key": ACCESS_KEY
    }
    payload = {
        "is_get_point_dict": "1",
        "point_id_list": ["83033", "83106", "83238"],
        "ps_id_list": [str(pid) for pid in plant_ids],
        "appkey": APP_KEY,
        "lang": "_en_US"
    }
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        power_map = {}
        battery_map = {}
        for item in data.get("result_data", {}).get("device_point_list", []):
            ps_id = str(item.get("ps_id"))
            power_val = item.get("p83033")
            battery_val_m = item.get("p83106")
            battery_val = item.get("p83238")
            if power_val is not None:
                power_w = float(power_val)
                power_map[ps_id] = round(power_w / 1000, 2)  # kW
            else:
                power_map[ps_id] = 0  # or 0, if you prefer
            if ps_id == "5258825" and battery_val_m is not None:
                battery_w_m = float(battery_val_m)
                if float(battery_val_m) != 0.0:
                    battery_w_m = battery_w_m*-1   # Invert the sign for this specific plant
                battery_map[ps_id] = round(battery_w_m / 1000, 2)  # kW
            elif ps_id != "5258825" and battery_val is not None:
                battery_w = float(battery_val)
                battery_map[ps_id] = round(battery_w / 1000, 2)  # kW
            else:
                battery_map[ps_id] = 'N/A'
        return power_map, battery_map
    except Exception as e:
        print(f"Error fetching plant power: {e}")
        return {}

