from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta

db = SQLAlchemy()

class Company(db.Model):
    __tablename__ = 'companies'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    mail = db.Column(db.String(128))
    phone = db.Column(db.String(32))
    logo = db.Column(db.String(256))  # You can store a URL or file path

    def __repr__(self):
        return f"<Company {self.name}>"

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String)
    email = db.Column(db.String)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'))

    def __repr__(self):
        return f"<User {self.name} ({self.email})>"

class Plant(db.Model):
    __tablename__ = 'plants'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    installed_power = db.Column(db.Float)
    location = db.Column(db.String(256))
    contract = db.Column(db.String(128))
    status = db.Column(db.String(64))
    plant_id = db.Column(db.String(64))
    num_invertors = db.Column(db.Integer)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'))
    hasBattery = db.Column(db.Boolean, default=False)
    min_price = db.Column(db.Float)
    trader_id = db.Column(db.Integer, db.ForeignKey('traders.id'))
    metering_point = db.Column(db.String(128))
    
    company = db.relationship('Company', backref='plants')
    trader = db.relationship('Trader', backref='plants')
    def __repr__(self):
        return f"<Plant {self.name}>"

class Invertor(db.Model):
    __tablename__ = 'invertors'
    id = db.Column(db.Integer, primary_key=True)
    make = db.Column(db.String(128), nullable=False)
    power = db.Column(db.Float)
    device_id = db.Column(db.String(64))
    device_sn = db.Column(db.String(64))
    ps_key_id = db.Column(db.String(64))
    status = db.Column(db.String(64))
    plant_id = db.Column(db.Integer, db.ForeignKey('plants.id'))

    plant = db.relationship('Plant', backref='invertors')

    def __repr__(self):
        return f"<Invertor {self.make} ({self.device_id})>"

class Data(db.Model):
    __tablename__ = 'data'
    id = db.Column(db.Integer, primary_key=True)
    ts = db.Column(db.DateTime, nullable=False, index=True, default=datetime.utcnow)
    power_in_w = db.Column(db.Float, nullable=False)
    invertor_id = db.Column(db.Integer, db.ForeignKey('invertors.id'), nullable=False, index=True)
    ps_id = db.Column(db.String(64), index=True)
    invertor = db.relationship('Invertor', backref='data')

    def __repr__(self):
        return f"<Data {self.ts} {self.power_in_w}W Invertor:{self.invertor_id}>"
    
class Price(db.Model):
    __tablename__ = 'prices'
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, index=True)
    hour = db.Column(db.Integer, nullable=False, index=True)
    price = db.Column(db.Float, nullable=False)

    def __repr__(self):
        return f"<Price {self.date} h{self.hour} = {self.price}>"

class Trader(db.Model):
    __tablename__ = 'traders'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    phone = db.Column(db.String(32))
    mail = db.Column(db.String(128))
    send_notification = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f"<Trader {self.name}>"
    
class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    id = db.Column(db.Integer, primary_key=True)
    ts = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    principal = db.Column(db.String(128), nullable=False)
    message = db.Column(db.Text, nullable=False)

    def __repr__(self):
        return f"<AuditLog {self.ts} {self.principal}: {self.message[:30]}>"
