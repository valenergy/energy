import os
from dotenv import load_dotenv
import requests
from cryptography.fernet import Fernet
from app.models import db, Company, AuditLog
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo 

load_dotenv()

ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY")
FERNET = Fernet(ENCRYPTION_KEY)

def encrypt_token(token):
    return FERNET.encrypt(token.encode()).decode()

def decrypt_token(token):
    return FERNET.decrypt(token.encode()).decode()

def refresh_tokens(company_id):
    company = Company.query.get(company_id)
    if not company or not company.refresh_token:
        return {"error": "Company or refresh token not found"}
    refresh_token = decrypt_token(company.refresh_token)
    ACCESS_KEY = os.environ.get("ACCESS_KEY")
    APP_KEY = os.environ.get("APP_KEY")
    payload = {
        "refresh_token": refresh_token,
        "appkey": APP_KEY
    }
    headers = {
        "content-type": "application/json",
        "x-access-key": ACCESS_KEY
    }
    TOKEN_URL = "https://gateway.isolarcloud.eu/openapi/apiManage/refreshToken"
    response = requests.post(TOKEN_URL, json=payload, headers=headers)
    response.raise_for_status()
    data = response.json()
    # Extract tokens
    new_access_token = data.get("access_token") or data["result_data"].get("access_token")
    new_refresh_token = data.get("refresh_token") or data["result_data"].get("refresh_token")
    expires_in = data.get("expires_in") or data["result_data"].get("expires_in")
    # Encrypt and store
    company.access_token = encrypt_token(new_access_token)
    company.refresh_token = encrypt_token(new_refresh_token)
    # Store access_token_expires_at
    if expires_in:
        company.access_token_expires_at = datetime.now(ZoneInfo("Europe/Sofia")) + timedelta(seconds=int(expires_in))
    entry = AuditLog(
        ts = datetime.now(ZoneInfo("Europe/Sofia")),
        principal=f"company_id={company_id}",
        message=f"OAuth tokens updated via refresh_tokens, expires in {expires_in} seconds"
    )
    db.session.add(entry)
    db.session.commit()
    return {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token,
        "expires_in": expires_in
    }

def refresh_tokens_huawei(company_id):
    from app.models import Company
    company = Company.query.get(company_id)
    if not company or not company.huawei_refresh_token:
        return {"error": "Company or Huawei refresh token not found"}

    client_id = os.environ.get("HUAWEI_CLIENT_ID")
    client_secret = os.environ.get("HUAWEI_CLIENT_SECRET")
    refresh_token = decrypt_token(company.huawei_refresh_token)
    token_url = "https://oauth2.fusionsolar.huawei.com/rest/dp/uidm/oauth2/v1/token"
    headers = {'content-type': 'application/x-www-form-urlencoded'}
    data = {
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token,
        'client_id': client_id,
        'client_secret': client_secret
    }

    response = requests.post(token_url, headers=headers, data=data)
    response.raise_for_status()
    resp_json = response.json()

    access_token = resp_json.get('access_token')
    new_refresh_token = resp_json.get('refresh_token')
    expires_in = resp_json.get('expires_in')

    if not (access_token and new_refresh_token and expires_in):
        return {"error": "Invalid response from Huawei"}

    # Encrypt and store
    company.huawei_access_token = encrypt_token(access_token)
    company.huawei_refresh_token = encrypt_token(new_refresh_token)
    company.huawei_expires_at = datetime.utcnow() + timedelta(seconds=int(expires_in))
    db.session.commit()

    return {
        "access_token": access_token,
        "refresh_token": new_refresh_token,
        "expires_in": expires_in
    }

def get_valid_access_token(company_id):
    company = Company.query.get(company_id)
    if not company or not company.access_token:
        return None
    now = datetime.now(ZoneInfo("Europe/Sofia"))
    expires_at = company.access_token_expires_at
    # Make expires_at timezone-aware if it's naive
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=ZoneInfo("Europe/Sofia"))
    # If token is expired or missing expiry, refresh it
    if not expires_at or expires_at < now:
        result = refresh_tokens(company_id)
        if "access_token" in result:
            return result["access_token"]
        return None
    return decrypt_token(company.access_token)

def get_valid_access_token_huawei(company_id):
    company = Company.query.get(company_id)
    if not company or not company.huawei_access_token:
        return None
    now = datetime.now(ZoneInfo("Europe/Sofia"))
    expires_at = company.huawei_expires_at
    # Make expires_at timezone-aware if it's naive
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=ZoneInfo("Europe/Sofia"))
    # If token is expired or missing expiry, refresh it
    if not expires_at or expires_at < now:
        result = refresh_tokens_huawei(company_id)
        if "access_token" in result:
            return result["access_token"]
        return None
    return decrypt_token(company.huawei_access_token)