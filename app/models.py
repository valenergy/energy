from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from flask_security import RoleMixin, UserMixin 

db = SQLAlchemy()

# Association table for users and roles
roles_users = db.Table(
    'roles_users',
    db.Column('id', db.Integer, primary_key=True),
    db.Column('user_id', db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
    db.Column('role_id', db.Integer, db.ForeignKey('roles.id', ondelete='CASCADE'), nullable=False),
    db.UniqueConstraint('user_id', 'role_id', name='uq_roles_users_user_role')
)

class Role(db.Model, RoleMixin):
    __tablename__ = 'roles'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    description = db.Column(db.String(255))

class Company(db.Model):
    __tablename__ = 'companies'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    mail = db.Column(db.String(128))
    phone = db.Column(db.String(32))
    logo = db.Column(db.String(256))
    refresh_token = db.Column(db.String(512))
    access_token = db.Column(db.String(512))
    access_token_expires_at = db.Column(db.DateTime)

    def __repr__(self):
        return f"<Company {self.name}>"

class User(db.Model, UserMixin):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String)
    email = db.Column(db.String, unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    active = db.Column(db.Boolean, default=True)
    fs_uniquifier = db.Column(db.String(64), unique=True, nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'))
    roles = db.relationship('Role', secondary=roles_users, backref=db.backref('users', lazy='dynamic'))
    last_login_at = db.Column(db.DateTime)
    current_login_at = db.Column(db.DateTime)
    last_login_ip = db.Column(db.String(64))
    current_login_ip = db.Column(db.String(64))
    login_count = db.Column(db.Integer, default=0)

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
    
class Device(db.Model):
    __tablename__ = 'devices'
    id = db.Column(db.Integer, primary_key=True)
    type_name = db.Column(db.String(128))
    ps_key = db.Column(db.String(64))
    device_sn = db.Column(db.String(64))
    dev_status = db.Column(db.String(16))
    device_type = db.Column(db.Integer)
    factory_name = db.Column(db.String(128))
    uuid = db.Column(db.Integer)
    device_name = db.Column(db.String(128))
    device_code = db.Column(db.Integer)
    ps_id = db.Column(db.Integer)
    device_model_id = db.Column(db.Integer)
    communication_dev_sn = db.Column(db.String(64))
    device_model_code = db.Column(db.String(64))
    plant_id = db.Column(db.Integer, db.ForeignKey('plants.id'), nullable=False)

    plant = db.relationship('Plant', backref='devices')

    def __repr__(self):
        return f"<Device {self.device_name} ({self.device_sn})>"

class Energy(db.Model):
    __tablename__ = 'energy'
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, index=True)
    start_period = db.Column(db.Time, nullable=False)
    end_period = db.Column(db.Time, nullable=False)
    duration_in_minutes = db.Column(db.Integer, nullable=False)
    trader_forecast = db.Column(db.Float)
    producer_forecast = db.Column(db.Float)
    yield_power = db.Column(db.Float)
    exported = db.Column(db.Float)
    plant_id = db.Column(db.Integer, db.ForeignKey('plants.id'), nullable=False, index=True)
    price = db.Column(db.Float)  # <-- changed from price_id

    plant = db.relationship('Plant', backref='energy')

    def __repr__(self):
        return f"<Energy {self.date} {self.start_period}-{self.end_period} Plant:{self.plant_id}>"
