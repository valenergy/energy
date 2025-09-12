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

def fetch_attachment():
    load_dotenv()
    download_folder = "attachments"
    imap_host = os.environ.get("IMAP_HOST")
    email_user = os.environ.get("EMAIL_USER")
    email_pass = os.environ.get("MAIL_PASSWORD")
    sender = os.environ.get("SENDER")
    with IMAPClient(imap_host) as server:
        server.login(email_user, email_pass)
        server.select_folder('INBOX')
        today = datetime.now().strftime("%d-%b-%Y")
        messages = server.search([
            'FROM', sender,
            'SINCE', today
        ])
        print(f"Found {len(messages)} messages from {sender} since {today}")
        for uid in reversed(messages):
            raw_message = server.fetch([uid], ['BODY[]'])[uid][b'BODY[]']
            message = pyzmail.PyzMessage.factory(raw_message)
            subject = message.get_subject()
            print(f"Processing email: {subject}")
            for part in message.mailparts:
                filename = part.filename
                # If subject contains "Мизия 2", set filename accordingly
                if filename and filename.endswith('.xlsx'):
                    if subject and "Мизия 2" in subject:
                        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
                        filename = f"ФЕЦ Мизия 2_{tomorrow}.xlsx"
                    if not os.path.isdir(download_folder):
                        os.makedirs(download_folder)
                    filepath = os.path.join(download_folder, filename)
                    with open(filepath, 'wb') as f:
                        f.write(part.get_payload())
    return None

def send_dam_schedulle_mail(filename=None):
    load_dotenv()
    sender = os.environ.get("EMAIL_USER")
    password = os.environ.get("MAIL_PASSWORD")
    recipient = os.environ.get("RECIPIENT")
    cc1 = sender
    cc2 = "h.bakalov@sig-solar.com"
    if filename is None:
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        filename = f"DAM_Schedulle_M13_{tomorrow}.xlsx"
    attachment_path = os.path.join("attachments", filename)

    # Create the email
    msg = MIMEMultipart()
    msg['From'] = sender
    msg['To'] = recipient
    msg['Cc'] = f"{cc1}, {cc2}"
    msg['Subject'] = f"DAM Schedulle M13 {filename.split('_')[-1].split('.')[0]}"
    body = "ФЕЦ Ток Инвест М13 с ИТН 32Z140000228916V няма да работи при цена под 35.15лв"
    msg.attach(MIMEText(body, 'plain'))

    # Attach the file
    try:
        with open(attachment_path, "rb") as f:
            part = MIMEApplication(f.read(), Name=filename)
            part['Content-Disposition'] = f'attachment; filename="{filename}"'
            msg.attach(part)
    except FileNotFoundError:
        print(f"Attachment not found: {attachment_path}")
        return False

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
        print("Email sent successfully.")
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False

if __name__ == "__main__":
    filepath = fetch_attachment(
        imap_host=os.environ.get("IMAP_HOST"),
        email_user=os.environ.get("EMAIL_USER"),
        email_pass=os.environ.get("MAIL_PASSWORD"),
        sender=os.environ.get("SENDER")
    )
    if filepath:
        print(f"Downloaded file: {filepath}")
    else:
        print("No Excel attachment found.")