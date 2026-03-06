from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


class Vehicle(db.Model):
    __tablename__ = 'vehicles'
    id            = db.Column(db.Integer, primary_key=True)
    plate         = db.Column(db.String(20),  unique=True, nullable=False)
    type          = db.Column(db.String(30),  nullable=False)   # truck_large / truck_medium / van / motorcycle / refrigerated
    capacity_kg   = db.Column(db.Float,       nullable=False)
    capacity_m3   = db.Column(db.Float,       nullable=False)
    driver_name   = db.Column(db.String(100))
    driver_phone  = db.Column(db.String(20))
    status        = db.Column(db.String(20),  default='available')  # available / on_route / maintenance
    home_lat      = db.Column(db.Float)
    home_lng      = db.Column(db.Float)
    notes         = db.Column(db.Text)

    dispatches = db.relationship('Dispatch', backref='vehicle', lazy='dynamic')

    TYPE_LABELS = {
        'truck_large':  'Large Truck',
        'truck_medium': 'Medium Truck',
        'van':          'Van',
        'motorcycle':   'Motorcycle',
        'refrigerated': 'Refrigerated Truck',
    }
    RATE_PER_KM = {
        'truck_large':  3.00,
        'truck_medium': 2.50,
        'van':          1.80,
        'motorcycle':   0.80,
        'refrigerated': 3.50,
    }
    TYPE_ICON = {
        'truck_large':  'fa-truck',
        'truck_medium': 'fa-truck',
        'van':          'fa-van-shuttle',
        'motorcycle':   'fa-motorcycle',
        'refrigerated': 'fa-snowflake',
    }

    def type_display(self):
        return self.TYPE_LABELS.get(self.type, self.type)

    def rate_per_km(self):
        return self.RATE_PER_KM.get(self.type, 2.50)

    def icon(self):
        return self.TYPE_ICON.get(self.type, 'fa-truck')


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
    priority            = db.Column(db.String(10), default='standard')  # standard / express / urgent
    status              = db.Column(db.String(20), default='pending')   # pending / dispatched / in_transit / delivered / cancelled
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
        """Returns full route: origin → intermediate stops → destination as list of dicts."""
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
            'pending':    'secondary',
            'dispatched': 'info',
            'in_transit': 'primary',
            'delivered':  'success',
            'cancelled':  'danger',
        }.get(self.status, 'secondary')


class ShipmentStop(db.Model):
    __tablename__ = 'shipment_stops'
    id          = db.Column(db.Integer, primary_key=True)
    shipment_id = db.Column(db.Integer, db.ForeignKey('shipments.id'), nullable=False)
    address     = db.Column(db.String(200), nullable=False)
    lat         = db.Column(db.Float, nullable=False)
    lng         = db.Column(db.Float, nullable=False)
    stop_order  = db.Column(db.Integer, nullable=False)
    stop_type   = db.Column(db.String(20), default='waypoint')   # waypoint / pickup / delivery
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
        'created':           ('fa-circle-plus',    'secondary'),
        'dispatched':        ('fa-truck-fast',      'info'),
        'picked_up':         ('fa-box-open',        'primary'),
        'in_transit':        ('fa-route',           'primary'),
        'checkpoint':        ('fa-location-dot',    'warning'),
        'out_for_delivery':  ('fa-truck',           'warning'),
        'delivered':         ('fa-circle-check',    'success'),
        'failed_delivery':   ('fa-circle-xmark',    'danger'),
        'cancelled':         ('fa-ban',             'danger'),
    }

    def icon(self):
        return self.EVENT_ICONS.get(self.event_type, ('fa-circle', 'secondary'))[0]

    def color(self):
        return self.EVENT_ICONS.get(self.event_type, ('fa-circle', 'secondary'))[1]
