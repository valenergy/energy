import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
from imapclient import IMAPClient
import pyzmail
import pandas as pd
from email.header import decode_header
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.mime.base import MIMEBase
from email import encoders
from app.models import db, Energy
import io
import math
    

def send_forecast_to_trader(plant_id):
    load_dotenv()
    sender = os.environ.get("EMAIL_USER")
    password = os.environ.get("MAIL_PASSWORD")
    recipient = os.environ.get("RECIPIENT")
    cc1 = sender
    cc2 = "h.bakalov@sig-solar.com"
    # Generate tomorrow's date
    tomorrow = (datetime.now() + timedelta(days=1)).date()
    if plant_id == 3:
        filename = f"DAM_Schedulle_M13_{tomorrow}.xlsx"
        body = "ФЕЦ Ток Инвест М13 с ИТН 32Z140000228916V няма да работи при цена под 35.15лв"
        subject = f"DAM Schedulle M13 {tomorrow}"
    elif plant_id == 9:
        filename = f"DAM_FORECAST_NIVIANIN_{tomorrow}.xlsx"
        body = "ФЕЦ Нивянин с ИТН 32Z140000246950T няма да работи при цена под 35.15лв"
        subject = f"DAM FORECAST {tomorrow}"
    else:
        return False, "Invalid plant"

    # Query Energy table for tomorrow's data for the plant
    energies = Energy.query.filter_by(date=tomorrow, plant_id=plant_id).order_by(Energy.start_period).all()
    data = []
    for idx, e in enumerate(energies):
        # Check if producer_forecast is missing
        if e.producer_forecast is None or str(e.producer_forecast).strip() == "":
            return False, "Producer forecast is missing for one or more intervals. Please save all forecasts before sending."
        start_time = e.start_period.strftime("%H:%M")
        # For the last interval, set end_period to tomorrow + 1 day at 00:00
        if idx == len(energies) - 1:
            next_day = tomorrow + timedelta(days=1)
            end_period_str = f"{next_day.strftime('%d/%m/%Y')} 00:00"
        else:
            end_time = e.end_period.strftime("%H:%M")
            end_period_str = f"{tomorrow.strftime('%d/%m/%Y')} {end_time}"
        start_period_str = f"{tomorrow.strftime('%d/%m/%Y')} {start_time}"
        data.append({
            "Start period": start_period_str,
            "End period": end_period_str,
            "Номиниран график (DA)": e.producer_forecast if e.producer_forecast is not None else ""
        })
    # Create DataFrame and save to XLSX in memory
    df = pd.DataFrame(data)
    xlsx_buffer = io.BytesIO()
    df.to_excel(xlsx_buffer, index=False)
    xlsx_buffer.seek(0)

    # Create the email
    msg = MIMEMultipart()
    msg['From'] = sender
    msg['To'] = recipient
    msg['Cc'] = f"{cc1}, {cc2}"
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    # Attach the file from memory with correct MIME type
    part = MIMEBase('application', 'vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    part.set_payload(xlsx_buffer.read())
    encoders.encode_base64(part)
    part.add_header('Content-Disposition', f'attachment; filename="{filename}"')
    msg.attach(part)

    # Send the email
    try:
        with smtplib.SMTP("smtp.sig-solar.com", 587) as server:
            server.starttls()
            server.login(sender, password)
            server.sendmail(
                sender,
                [recipient, cc1, cc2],
                msg.as_string()
            )
        return True, "Email sent successfully."
    except Exception as e:
        return False, "Email is not sent successfully."
    

def update_trader_forecast_from_mail(date_str, plant_id):
    sender = os.environ.get("SENDER")
    imap_host = os.environ.get("IMAP_HOST")
    email_user = os.environ.get("EMAIL_USER")
    email_pass = os.environ.get("MAIL_PASSWORD")
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    next_day_str = (date_obj + timedelta(days=1)).strftime("%Y-%m-%d")

    # Set filename pattern based on plant_id
    if plant_id == 3:
        filename_pattern = f"DAM_Schedulle_M13_{next_day_str}"
    elif plant_id == 9:
        filename_pattern = f"DAM_FORECAST_NIVIANIN_{next_day_str}"
    else:
        filename_pattern = None  # Or handle other plant_ids as needed

    if not filename_pattern:
        return False  # No pattern for this plant_id

    with IMAPClient(imap_host) as server:
        server.login(email_user, email_pass)
        server.select_folder('INBOX')
        search_date = datetime.strptime(date_str, "%Y-%m-%d").strftime("%d-%b-%Y")
        messages = server.search(['FROM', sender, 'ON', search_date])
        for uid in reversed(messages):
            raw_message = server.fetch([uid], ['BODY[]'])[uid][b'BODY[]']
            message = pyzmail.PyzMessage.factory(raw_message)
            for part in message.mailparts:
                filename = part.filename
                if filename and filename_pattern in filename and filename.endswith('.xlsx'):
                    # Read the XLSX file from the email attachment
                    df = pd.read_excel(part.get_payload())
                    # Expect columns: Start period, End period, Номиниран график (DA)
                    for _, row in df.iterrows():
                        start_str = str(row['Start period'])
                        end_str = str(row['End period'])
                        forecast = row['Номиниран график (DA)']
                        # If forecast is empty or NaN, store as 0
                        if pd.isna(forecast) or forecast == "" or (isinstance(forecast, float) and math.isnan(forecast)):
                            forecast = 0
                        start_dt = pd.to_datetime(start_str, dayfirst=True)
                        end_dt = pd.to_datetime(end_str, dayfirst=True)
                        # Find or create Energy entry
                        energy = Energy.query.filter_by(
                            date=start_dt.date(),
                            start_period=start_dt.time(),
                            plant_id=plant_id
                        ).first()
                        if energy:
                            energy.trader_forecast = forecast
                        else:
                            energy = Energy(
                                date=start_dt.date(),
                                start_period=start_dt.time(),
                                end_period=end_dt.time(),
                                duration_in_minutes=int((end_dt - start_dt).total_seconds() // 60),
                                trader_forecast=forecast,
                                producer_forecast=None,
                                yield_power=None,
                                exported=None,
                                plant_id=plant_id,
                                price=None
                            )
                            db.session.add(energy)
                    db.session.commit()
                    return True  # Success
    return False  # Not found or not updated
