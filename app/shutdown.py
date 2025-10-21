from app.login_helper import get_valid_access_token
from app.models import Plant, Company
import requests
import os


def shutdown_plant_via_ems(ems_uuid, plant_id):
    ACCESS_KEY = os.environ.get("ACCESS_KEY")
    APP_KEY = os.environ.get("APP_KEY")

    plant = Plant.query.get(plant_id)
    if not plant:
        return {"error": "Plant not found"}
    access_token = get_valid_access_token(plant.company_id)

    url = "https://gateway.isolarcloud.eu/openapi/platform/paramSetting"
    headers = {
        "authorization": f"Bearer {access_token}",
        "content-type": "application/json",
        "x-access-key": ACCESS_KEY
    }
    payload = {
        "set_type": 0,
        "uuid": str(ems_uuid),
        "task_name": "Shutdown plant",
        "expire_second": 120,
        "param_list": [
            {"param_code": 10086, "set_value": "4"},
            {"param_code": 10089, "set_value": "-2"}
        ],
        "appkey": APP_KEY,
        "lang": "_en_US"
    }
    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 401:
            # Refresh token and retry
            access_token = get_valid_access_token(plant.company_id)
            headers["authorization"] = f"Bearer {access_token}"
            response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": str(e)}

def shutdown_plant_via_device(uuid_str, plant_id):
    print(f"Shutting down plant_id {plant_id} via device uuid {uuid_str}")
    ACCESS_KEY = os.environ.get("ACCESS_KEY")
    APP_KEY = os.environ.get("APP_KEY")
    access_token = get_valid_access_token(Company.query.get(Plant.query.get(plant_id).company_id).id)
    url = "https://gateway.isolarcloud.eu/openapi/platform/paramSetting"
    headers = {
        "authorization": f"Bearer {access_token}",
        "content-type": "application/json",
        "x-access-key": ACCESS_KEY
    }
    payload = {
        "set_type": 0,
        "uuid": uuid_str,
        "task_name": "Shutdown",
        "expire_second": 120,
        "param_list": [
            {
                "param_code": 10011,
                "set_value": "206"  # 206 for stop
            }
        ],
        "appkey": APP_KEY,
        "lang": "_en_US"
    }
    response = requests.post(url, headers=headers, json=payload)
    return response.json()

