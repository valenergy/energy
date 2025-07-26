import os
from dotenv import load_dotenv
from datetime import datetime
from imapclient import IMAPClient
import pyzmail
import pandas as pd
from email.header import decode_header

def fetch_excel_attachment(imap_host, email_user, email_pass, sender, download_folder="attachments"):
    load_dotenv()
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
        for uid in reversed(messages):
            raw_message = server.fetch([uid], ['BODY[]'])[uid][b'BODY[]']
            message = pyzmail.PyzMessage.factory(raw_message)
            for part in message.mailparts:
                filename = part.filename
                if filename and filename.endswith('.xlsx'):
                    if not os.path.isdir(download_folder):
                        os.makedirs(download_folder)
                    filepath = os.path.join(download_folder, today + ".xlsx")
                    with open(filepath, 'wb') as f:
                        f.write(part.get_payload())
                    return filepath
    return None

if __name__ == "__main__":
    filepath = fetch_excel_attachment(
        imap_host=os.environ.get("IMAP_HOST"),
        email_user=os.environ.get("EMAIL_USER"),
        email_pass=os.environ.get("MAIL_PASSWORD"),
        sender=os.environ.get("SENDER")
    )
    if filepath:
        print(f"Downloaded file: {filepath}")
    else:
        print("No Excel attachment found.")