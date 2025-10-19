import os
import requests
from app.models import Plant
from app.login_helper import get_valid_access_token

def get_new_plants(company_id):
    access_token = get_valid_access_token(company_id)
    ACCESS_KEY = os.environ.get("ACCESS_KEY")
    APP_KEY = os.environ.get("APP_KEY")

    url = "https://gateway.isolarcloud.eu/openapi/platform/queryPowerStationList"
    headers = {
        "authorization": f"Bearer {access_token}",
        "content-type": "application/json",
        "x-access-key": ACCESS_KEY
    }
    payload = {
        "page": 1,
        "size": 100,
        "appkey": APP_KEY,
        "lang": "_en_US"
    }
    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    data = response.json()
    new_plants = []
    # Get all plant_ids from DB
    from app import db
    existing_ids = {str(p.plant_id) for p in Plant.query.all()}
    # Check for new plants
    for plant in data.get("result_data", {}).get("pageList", []):
        if str(plant["ps_id"]) not in existing_ids:
            plant["make"] = "SUNGROW"
            new_plants.append(plant)
    return new_plants