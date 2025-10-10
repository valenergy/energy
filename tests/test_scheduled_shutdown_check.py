import sys
from pathlib import Path
import pytest

# ensure project root is on sys.path so `import app` and `import server` work
project_root = str(Path(__file__).resolve().parents[1])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from server import app as flask_app
from app import db as _db

@pytest.fixture
def app():
    flask_app.config['TESTING'] = True
    flask_app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    # disable things that may interact with external services if present
    flask_app.config.setdefault('WTF_CSRF_ENABLED', False)
    with flask_app.app_context():
        _db.create_all()
        yield flask_app
        _db.session.remove()
        _db.drop_all()

from unittest.mock import patch, MagicMock
from app.models import Plant, Price, Device, Invertor, db
from server import scheduled_shutdown_check
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

@pytest.fixture
def app_with_test_db(app):
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()

@pytest.fixture
def setup_test_data(app_with_test_db):
    with app_with_test_db.app_context():
        # Create a plant with min_price
        plant = Plant(
            name="Test Plant",
            min_price=50,
            status="ON",
            hasBattery=False
        )
        db.session.add(plant)
        db.session.commit()

        # Add a price below min_price for current period
        now_sofia = datetime.now(ZoneInfo("Europe/Sofia"))
        minutes_since_midnight = now_sofia.hour * 60 + now_sofia.minute
        period = minutes_since_midnight // 15 + 1 - 3
        product = f"QH {period}"
        price = Price(
            date=now_sofia.date(),
            product=product,
            price=20,  # below min_price
            hour=now_sofia.hour
        )
        db.session.add(price)
        db.session.commit()

        # Add a device for fallback
        device = Device(
            plant_id=plant.id,
            device_type=1,
            uuid=123456
        )
        db.session.add(device)
        db.session.commit()

        yield plant, price, device

@patch('app.shutdown.shutdown_plant_via_device')
def test_scheduled_shutdown_check(mock_shutdown, app_with_test_db, setup_test_data):
    mock_shutdown.return_value = {"result": "success"}
    plant, price, device = setup_test_data
    with app_with_test_db.app_context():
        scheduled_shutdown_check()
        updated_plant = Plant.query.get(plant.id)
        assert updated_plant.status == "OFF"
        mock_shutdown.assert_called_once()