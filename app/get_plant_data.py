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


def get_plant_data():
    url = "https://gateway.isolarcloud.eu/openapi/getPowerStationList"
    headers = {
        "Content-Type": "application/json",
        "x-access-key": "05ikbup0ubwr900fa9imbifb9ppffxyn"
    }
    data = {
        "curPage": 1,
        "size": 100,
        "appkey": "5145B41888F6FDFED1778BCBB96D45FD",
        "token": "528906_3ea0a80b07ec4bc99e1083d1daa3c68e",
        "lang": "_en_US"
    }

    exclude_ids = {5722350, 5193962, 5266067}

    response = requests.post(url, headers=headers, json=data)

    if response.status_code == 200:
        resp_json = response.json()
        stations = resp_json.get("result_data", {}).get("pageList", [])
        result = []
        for station in stations:
            if station.get("ps_id") not in exclude_ids:
                curr_power = station.get("curr_power", {})
                value = curr_power.get("value", "--")
                unit = curr_power.get("unit", "kW")
                # Convert W to kW if needed
                if unit == "W" and value not in ("--", None):
                    try:
                        value = float(value) / 1000
                    except Exception:
                        value = "--"
                result.append({
                    "name": station.get("ps_name"),
                    "ps_id": station.get("ps_id"),
                    "current_power": value
                })
        return result
    else:
        return []

def get_live_active_power():
    url = "https://gateway.isolarcloud.eu/openapi/getPVInverterRealTimeData"
    headers = {
        "Content-Type": "application/json",
        "x-access-key": "05ikbup0ubwr900fa9imbifb9ppffxyn"
    }

    # Fetch ps_key_id from the Invertor table
    ps_key_list = [inv.ps_key_id for inv in Invertor.query.all()]

    data = {
        "ps_key_list": ps_key_list,
        "appkey": "5145B41888F6FDFED1778BCBB96D45FD",
        "token": "528906_3ea0a80b07ec4bc99e1083d1daa3c68e",
        "lang": "_en_US"
    }

    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 200:
        return response.json()
    else:
        return {"error": response.status_code, "message": response.text}

def get_live_power_by_ps_id(live_power_response):
    """Returns a dict: {ps_id: live_power_kw}"""
    ps_power = {}
    device_points = live_power_response.get("result_data", {}).get("device_point_list", [])
    for dp in device_points:
        device = dp.get("device_point", {})
        ps_id = device.get("ps_id")
        p24 = device.get("p24")
        if ps_id is not None and p24 is not None:
            try:
                p24 = float(p24)
            except Exception:
                continue
            ps_power[ps_id] = ps_power.get(ps_id, 0) + p24
    # Convert W to kW
    for ps_id in ps_power:
        ps_power[ps_id] = round(ps_power[ps_id] / 1000, 3)
    return ps_power

def get_plant_data_with_live_power():
    plant_data = get_plant_data()  # your existing function
    live_power_response = get_live_active_power()  # call your live power API
    live_power_map = get_live_power_by_ps_id(live_power_response)
    for plant in plant_data:
        plant['live_power'] = live_power_map.get(plant['ps_id'], 0)
    return plant_data