from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


class Driver(db.Model):
    __tablename__ = 'drivers'
    id                  = db.Column(db.Integer, primary_key=True)
    name                = db.Column(db.String(100), nullable=False)
    license_number      = db.Column(db.String(20),  unique=True)
    license_class       = db.Column(db.String(20))   # 1종 대형 / 1종 보통 / 2종 보통
    phone               = db.Column(db.String(20))
    email               = db.Column(db.String(100))
    vehicle_id          = db.Column(db.Integer, db.ForeignKey('vehicles.id'))
    working_hours_today = db.Column(db.Float, default=0)  # hours worked today
    total_deliveries    = db.Column(db.Integer, default=0)
    on_time_deliveries  = db.Column(db.Integer, default=0)
    status              = db.Column(db.String(20), default='active')  # active / off_duty / rest
    joined_at           = db.Column(db.DateTime, default=datetime.utcnow)
    notes               = db.Column(db.Text)

    vehicle = db.relationship('Vehicle', backref='driver', uselist=False,
                              foreign_keys=[vehicle_id])

    def on_time_rate(self):
        if self.total_deliveries == 0:
            return 0.0
        return round(self.on_time_deliveries / self.total_deliveries * 100, 1)

    def is_over_hours(self):
        return self.working_hours_today > 8.0

    def performance_score(self):
        rate  = self.on_time_rate()
        vol   = min(100, self.total_deliveries / 5)
        return round(rate * 0.7 + vol * 0.3, 1)

    def status_label(self):
        return {'active': '근무중', 'off_duty': '비번', 'rest': '휴식중'}.get(self.status, self.status)


class Vehicle(db.Model):
    __tablename__ = 'vehicles'
    id                   = db.Column(db.Integer, primary_key=True)
    plate                = db.Column(db.String(20),  unique=True, nullable=False)
    type                 = db.Column(db.String(30),  nullable=False)
    capacity_kg          = db.Column(db.Float,        nullable=False)
    capacity_m3          = db.Column(db.Float,        nullable=False)
    driver_name          = db.Column(db.String(100))   # kept for compatibility
    driver_phone         = db.Column(db.String(20))
    status               = db.Column(db.String(20),  default='available')
    home_lat             = db.Column(db.Float)
    home_lng             = db.Column(db.Float)
    fuel_efficiency_kmpl = db.Column(db.Float, default=10.0)  # km/L
    fuel_type            = db.Column(db.String(20), default='diesel')
    mileage_km           = db.Column(db.Integer, default=0)
    notes                = db.Column(db.Text)

    dispatches          = db.relationship('Dispatch',           backref='vehicle', lazy='dynamic')
    maintenance_records = db.relationship('MaintenanceRecord',  backref='vehicle', lazy='dynamic',
                                          cascade='all, delete-orphan')

    TYPE_LABELS = {
        'truck_large':  '대형 트럭',
        'truck_medium': '중형 트럭',
        'van':          '밴',
        'motorcycle':   '오토바이',
        'refrigerated': '냉동 트럭',
    }
    RATE_PER_KM = {
        'truck_large':  3.0,
        'truck_medium': 2.5,
        'van':          1.8,
        'motorcycle':   0.8,
        'refrigerated': 3.5,
    }
    TYPE_ICON = {
        'truck_large':  'fa-truck',
        'truck_medium': 'fa-truck',
        'van':          'fa-van-shuttle',
        'motorcycle':   'fa-motorcycle',
        'refrigerated': 'fa-snowflake',
    }
    DEFAULT_EFFICIENCY = {
        'truck_large': 8.5, 'truck_medium': 11.0, 'van': 14.5,
        'motorcycle': 32.0, 'refrigerated': 7.5,
    }

    def type_display(self):
        return self.TYPE_LABELS.get(self.type, self.type)

    def rate_per_km(self):
        return self.RATE_PER_KM.get(self.type, 2.5)

    def icon(self):
        return self.TYPE_ICON.get(self.type, 'fa-truck')

    def fuel_cost_per_km(self, fuel_price_krw=1650):
        eff = self.fuel_efficiency_kmpl or self.DEFAULT_EFFICIENCY.get(self.type, 10.0)
        return round(fuel_price_krw / eff)

    def trip_fuel_cost(self, distance_km, fuel_price_krw=1650):
        return round(self.fuel_cost_per_km(fuel_price_krw) * distance_km)

    def next_maintenance(self):
        return (self.maintenance_records
                .filter(MaintenanceRecord.status == 'scheduled')
                .order_by(MaintenanceRecord.scheduled_date)
                .first())

    def overdue_maintenance(self):
        return self.maintenance_records.filter_by(status='overdue').count()

    def maintenance_list(self):
        return (self.maintenance_records
                .order_by(MaintenanceRecord.scheduled_date.desc())
                .all())


class MaintenanceRecord(db.Model):
    __tablename__ = 'maintenance_records'
    id               = db.Column(db.Integer, primary_key=True)
    vehicle_id       = db.Column(db.Integer, db.ForeignKey('vehicles.id'), nullable=False)
    maintenance_type = db.Column(db.String(50))
    scheduled_date   = db.Column(db.DateTime)
    completed_date   = db.Column(db.DateTime)
    cost             = db.Column(db.Integer, default=0)   # KRW
    notes            = db.Column(db.Text)
    status           = db.Column(db.String(20), default='scheduled')  # scheduled / completed / overdue
    mileage_km       = db.Column(db.Integer, default=0)

    def status_label(self):
        return {'scheduled': '예정', 'completed': '완료', 'overdue': '기한초과'}.get(self.status, self.status)

    def status_color(self):
        return {'scheduled': 'primary', 'completed': 'success', 'overdue': 'danger'}.get(self.status, 'secondary')


class Shipment(db.Model):
    __tablename__ = 'shipments'
    id                  = db.Column(db.Integer,  primary_key=True)
    shipment_number     = db.Column(db.String(20), unique=True, nullable=False)
    customer_name       = db.Column(db.String(100), nullable=False)
    customer_phone      = db.Column(db.String(20))
    customer_email      = db.Column(db.String(100))
    origin_address      = db.Column(db.String(200), nullable=False)
    origin_lat          = db.Column(db.Float, nullable=False)
    origin_lng          = db.Column(db.Float, nullable=False)
    destination_address = db.Column(db.String(200), nullable=False)
    destination_lat     = db.Column(db.Float, nullable=False)
    destination_lng     = db.Column(db.Float, nullable=False)
    weight_kg           = db.Column(db.Float,  default=0)
    volume_m3           = db.Column(db.Float,  default=0)
    priority            = db.Column(db.String(10), default='standard')
    status              = db.Column(db.String(20), default='pending')
    freight_cost        = db.Column(db.Float)
    distance_km         = db.Column(db.Float)
    notes               = db.Column(db.Text)
    created_at          = db.Column(db.DateTime, default=datetime.utcnow)
    estimated_delivery  = db.Column(db.DateTime)
    actual_delivery     = db.Column(db.DateTime)

    stops           = db.relationship('ShipmentStop',  backref='shipment', lazy=True,
                                      cascade='all, delete-orphan', order_by='ShipmentStop.stop_order')
    dispatch        = db.relationship('Dispatch',       backref='shipment', uselist=False,
                                      cascade='all, delete-orphan')
    tracking_events = db.relationship('TrackingEvent', backref='shipment', lazy=True,
                                      cascade='all, delete-orphan', order_by='TrackingEvent.created_at')

    def all_stops(self):
        route = [{'address': self.origin_address, 'lat': self.origin_lat,
                  'lng': self.origin_lng, 'type': 'origin'}]
        for s in self.stops:
            route.append({'address': s.address, 'lat': s.lat, 'lng': s.lng,
                          'type': s.stop_type, 'id': s.id, 'order': s.stop_order})
        route.append({'address': self.destination_address, 'lat': self.destination_lat,
                      'lng': self.destination_lng, 'type': 'destination'})
        return route

    def status_color(self):
        return {
            'pending': 'secondary', 'dispatched': 'info',
            'in_transit': 'primary', 'delivered': 'success', 'cancelled': 'danger',
        }.get(self.status, 'secondary')

    def sla_status(self):
        """SLA compliance: express=1day, standard=3days, urgent=same day."""
        if self.status != 'delivered' or not self.actual_delivery:
            return None
        sla_hours = {'urgent': 24, 'express': 36, 'standard': 72}.get(self.priority, 72)
        deadline = self.created_at + __import__('datetime').timedelta(hours=sla_hours)
        return 'met' if self.actual_delivery <= deadline else 'missed'


class ShipmentStop(db.Model):
    __tablename__ = 'shipment_stops'
    id          = db.Column(db.Integer, primary_key=True)
    shipment_id = db.Column(db.Integer, db.ForeignKey('shipments.id'), nullable=False)
    address     = db.Column(db.String(200), nullable=False)
    lat         = db.Column(db.Float, nullable=False)
    lng         = db.Column(db.Float, nullable=False)
    stop_order  = db.Column(db.Integer, nullable=False)
    stop_type   = db.Column(db.String(20), default='waypoint')
    notes       = db.Column(db.Text)


class Dispatch(db.Model):
    __tablename__ = 'dispatches'
    id           = db.Column(db.Integer, primary_key=True)
    shipment_id  = db.Column(db.Integer, db.ForeignKey('shipments.id'), unique=True, nullable=False)
    vehicle_id   = db.Column(db.Integer, db.ForeignKey('vehicles.id'),  nullable=False)
    assigned_at  = db.Column(db.DateTime, default=datetime.utcnow)
    driver_notes = db.Column(db.Text)


class TrackingEvent(db.Model):
    __tablename__ = 'tracking_events'
    id               = db.Column(db.Integer, primary_key=True)
    shipment_id      = db.Column(db.Integer, db.ForeignKey('shipments.id'), nullable=False)
    event_type       = db.Column(db.String(30), nullable=False)
    description      = db.Column(db.Text)
    location_address = db.Column(db.String(200))
    location_lat     = db.Column(db.Float)
    location_lng     = db.Column(db.Float)
    created_at       = db.Column(db.DateTime, default=datetime.utcnow)

    EVENT_ICONS = {
        'created':          ('fa-circle-plus',   'secondary'),
        'dispatched':       ('fa-truck-fast',    'info'),
        'picked_up':        ('fa-box-open',      'primary'),
        'in_transit':       ('fa-route',         'primary'),
        'checkpoint':       ('fa-location-dot',  'warning'),
        'out_for_delivery': ('fa-truck',         'warning'),
        'delivered':        ('fa-circle-check',  'success'),
        'failed_delivery':  ('fa-circle-xmark',  'danger'),
        'cancelled':        ('fa-ban',           'danger'),
    }

    def icon(self):
        return self.EVENT_ICONS.get(self.event_type, ('fa-circle', 'secondary'))[0]

    def color(self):
        return self.EVENT_ICONS.get(self.event_type, ('fa-circle', 'secondary'))[1]
