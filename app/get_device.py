import os
import requests
from app.models import Device
from app import db

def get_and_store_devices(ps_id, plant_id, access_token):
    ACCESS_KEY = os.environ.get("ACCESS_KEY")
    APP_KEY = os.environ.get("APP_KEY")
    url = "https://gateway.isolarcloud.eu/openapi/platform/getDeviceListByPsId"
    headers = {
        "authorization": f"Bearer {access_token}",
        "content-type": "application/json",
        "x-access-key": ACCESS_KEY
    }
    payload = {
        "ps_id": str(ps_id),
        "page": 1,
        "size": 100,
        "appkey": APP_KEY,
        "lang": "_en_US"
    }
    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    data = response.json()
    devices = data.get("result_data", {}).get("pageList", [])
    for d in devices:
        device = Device(
            plant_id=plant_id,
            ps_id=d.get("ps_id"),
            uuid=d.get("uuid"),
            device_sn=d.get("device_sn"),
            device_name=d.get("device_name"),
            device_type=d.get("device_type"),
            type_name=d.get("type_name"),
            factory_name=d.get("factory_name"),
            device_model_id=d.get("device_model_id"),
            device_model_code=d.get("device_model_code"),
            communication_dev_sn=d.get("communication_dev_sn"),
            dev_status=d.get("dev_status"),
            device_code=d.get("device_code"),
            ps_key=d.get("ps_key")
        )
        db.session.add(device)
    db.session.commit()