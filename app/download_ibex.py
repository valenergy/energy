import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
from server import app, log_audit
from app.models import db, Price  # Import your Price model


with app.app_context():
    # Fetch the page with a browser-like User-Agent
    url = "https://ibex.bg/dam-history.php"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }
    response = requests.get(url, headers=headers)
    response.raise_for_status()

    # Parse with BeautifulSoup
    soup = BeautifulSoup(response.text, "html.parser")

    # Find the table
    table = soup.find("table", {"id": "dam-history"})
    if table is None:
        log_audit("download_ibex", "Could not find a table with id 'dam-history' on the page.")
        exit(1)

    # Use pandas to read the HTML table
    df = pd.read_html(str(table))[0]

    # Clean column names (remove extra spaces, unify case)
    df.columns = [col.strip() for col in df.columns]
    # Convert 'Price (BGN)' to float, handling comma as decimal separator
    def fix_price(val):
        val = str(val).replace(' ', '')
        # Handle comma as decimal separator, e.g. "-0,04" or "143,28"
        if ',' in val:
            return float(val.replace(',', '.'))
        # Handle numbers like -004 or 29030 (last two digits are decimals)
        m = re.match(r"^(-?)(\d+)$", val)
        if m:
            sign, digits = m.groups()
            if len(digits) > 2:
                return float(f"{sign}{digits[:-2]}.{digits[-2:]}")
            else:
                return float(f"{sign}0.{digits.zfill(2)}")
        return float('nan')

    df['Price (BGN)'] = df['Price (BGN)'].apply(fix_price)
    # Find the last two available dates
    last_two_dates = sorted(df['Date'].unique())[-2:]

    # Extract and store BGN price and hour for each of the last two dates into DB
    for date in last_two_dates:
        day_df = df[df['Date'] == date][['Date', 'Hour', 'Price (BGN)']]
        for _, row in day_df.iterrows():
            # Check if price already exists to avoid duplicates
            existing = Price.query.filter_by(date=row['Date'], hour=row['Hour']).first()
            if existing:
                existing.price = row['Price (BGN)']
            else:
                price_entry = Price(
                    date=row['Date'],
                    hour=row['Hour'],
                    price=row['Price (BGN)']
                )
                db.session.add(price_entry)
        db.session.commit()
        log_audit("download_ibex", f"Stored BGN prices for {date} in the database")