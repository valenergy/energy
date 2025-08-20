import os
from dotenv import load_dotenv
import requests
from cryptography.fernet import Fernet
from app.models import db, Company, AuditLog
from datetime import datetime
from zoneinfo import ZoneInfo 

load_dotenv()

ACCESS_KEY = os.environ.get("ACCESS_KEY")
APP_KEY = os.environ.get("APP_KEY")
ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY")
FERNET = Fernet(ENCRYPTION_KEY)

TOKEN_URL = "https://gateway.isolarcloud.eu/openapi/apiManage/refreshToken"

def encrypt_token(token):
    return FERNET.encrypt(token.encode()).decode()

def decrypt_token(token):
    return FERNET.decrypt(token.encode()).decode()

def refresh_tokens(company_id):
    company = Company.query.get(company_id)
    if not company or not company.refresh_token:
        raise Exception("Company or refresh token not found")
    refresh_token = decrypt_token(company.refresh_token)
    payload = {
        "refresh_token": refresh_token,
        "appkey": APP_KEY
    }
    headers = {
        "content-type": "application/json",
        "x-access-key": ACCESS_KEY
    }
    response = requests.post(TOKEN_URL, json=payload, headers=headers)
    response.raise_for_status()
    data = response.json()
    # Extract tokens
    new_access_token = data.get("access_token") or data["result_data"].get("access_token")
    new_refresh_token = data.get("refresh_token") or data["result_data"].get("refresh_token")
    # Encrypt and store
    company.access_token = encrypt_token(new_access_token)
    company.refresh_token = encrypt_token(new_refresh_token)
    entry = AuditLog(
        ts = datetime.now(ZoneInfo("Europe/Sofia")),
        principal=f"company_id={company_id}",
        message="OAuth tokens updated via refresh_tokens, expires ib {data.get('expires_in') or data['result_data'].get('expires_in')}"
    )
    db.session.add(entry)
    db.session.commit()
    return {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token,
        "expires_in": data.get("expires_in") or data["result_data"].get("expires_in")
    }

def get_access_token(company_id):
    company = Company.query.get(company_id)
    if company and company.access_token:
        return decrypt_token(company.access_token)
    return None