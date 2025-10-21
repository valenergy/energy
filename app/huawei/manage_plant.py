import requests
from app.login_helper import get_valid_access_token_huawei

def stop_plant_huawei(company_id, plant_code):
    access_token = get_valid_access_token_huawei(company_id)
    if not access_token:
        return {"error": "No valid access token"}
    url = "https://eu5.fusionsolar.huawei.com/rest/openapi/pvms/nbi/v2/control/active-power-control/async-task"
    headers = {
        "authorization": f"Bearer {access_token}",
        "content-type": "application/json"
    }
    payload = {
        "tasks": [
            {
                "plantCode": plant_code,
                "controlMode": "6",
                "controlInfo": {
                    "maxGridFeedInPower": 0,
                    "limitationMode": 0
                }
            }
        ]
    }
    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    return response.json()

def start_plant_huawei(company_id, plant_code):
    access_token = get_valid_access_token_huawei(company_id)
    if not access_token:
        return {"error": "No valid access token"}
    url = "https://eu5.fusionsolar.huawei.com/rest/openapi/pvms/nbi/v2/control/active-power-control/async-task"
    headers = {
        "authorization": f"Bearer {access_token}",
        "content-type": "application/json"
    }
    payload = {
        "tasks": [
            {
                "plantCode": plant_code,
                "controlMode": "0"
            }
        ]
    }
    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    return response.json()