from models import db, Vehicle, Shipment, ShipmentStop, Dispatch, TrackingEvent
from datetime import datetime, timedelta
import math, random

# ── Korean city coordinates ──────────────────────────────────────────────────
CITIES = {
    'Seoul':    (37.5665, 126.9780, 'Seoul, South Korea'),
    'Busan':    (35.1796, 129.0756, 'Busan, South Korea'),
    'Daegu':    (35.8714, 128.6014, 'Daegu, South Korea'),
    'Incheon':  (37.4563, 126.7052, 'Incheon, South Korea'),
    'Gwangju':  (35.1595, 126.8526, 'Gwangju, South Korea'),
    'Daejeon':  (36.3504, 127.3845, 'Daejeon, South Korea'),
    'Ulsan':    (35.5384, 129.3114, 'Ulsan, South Korea'),
    'Suwon':    (37.2636, 127.0286, 'Suwon, South Korea'),
    'Changwon': (35.2280, 128.6811, 'Changwon, South Korea'),
    'Goyang':   (37.6564, 126.8350, 'Goyang, South Korea'),
    'Jeonju':   (35.8242, 127.1480, 'Jeonju, South Korea'),
    'Cheongju': (36.6424, 127.4890, 'Cheongju, South Korea'),
    'Pohang':   (36.0190, 129.3435, 'Pohang, South Korea'),
    'Ansan':    (37.3219, 126.8309, 'Ansan, South Korea'),
}

# ── Vehicle definitions ───────────────────────────────────────────────────────
# plate, type, cap_kg, cap_m3, driver_name, driver_phone, status, home_city
VEHICLES = [
    ('TMS-L001', 'truck_large',  15000, 60.0, 'Kim Daehan',   '010-1234-5678', 'available',   'Seoul'),
    ('TMS-L002', 'truck_large',  15000, 60.0, 'Lee Jihoon',   '010-2345-6789', 'on_route',    'Busan'),
    ('TMS-M001', 'truck_medium',  5000, 25.0, 'Park Suji',    '010-3456-7890', 'available',   'Daegu'),
    ('TMS-M002', 'truck_medium',  5000, 25.0, 'Choi Minseo',  '010-4567-8901', 'on_route',    'Daejeon'),
    ('TMS-V001', 'van',           1500,  8.0, 'Jung Yuna',    '010-5678-9012', 'available',   'Incheon'),
    ('TMS-V002', 'van',           1500,  8.0, 'Han Junho',    '010-6789-0123', 'available',   'Suwon'),
    ('TMS-V003', 'van',           1500,  8.0, 'Im Soyeon',    '010-7890-1234', 'maintenance', 'Gwangju'),
    ('TMS-R001', 'refrigerated',  8000, 35.0, 'Yoon Seokjin', '010-8901-2345', 'on_route',    'Ulsan'),
    ('TMS-MC01', 'motorcycle',     100,  0.5, 'Kang Hyejin',  '010-9012-3456', 'available',   'Goyang'),
    ('TMS-MC02', 'motorcycle',     100,  0.5, 'Shin Dongwoo', '010-0123-4567', 'available',   'Ansan'),
]

# ── Shipment definitions ──────────────────────────────────────────────────────
# customer, phone, origin_city, dest_city, weight_kg, volume_m3, priority, status, days_ago, vehicle_plate
SHIPMENTS = [
    # ── Delivered ──────────────────────────────────────────────────────────
    ('TechCorp Korea',    '02-1234-5678', 'Seoul',   'Busan',    1200, 4.5, 'express',  'delivered',   10, 'TMS-L001'),
    ('Samsung Partners',  '02-2345-6789', 'Incheon', 'Daegu',     800, 3.2, 'standard', 'delivered',    8, 'TMS-M001'),
    ('LG Electronics',    '02-3456-7890', 'Busan',   'Seoul',    2500,10.0, 'urgent',   'delivered',    6, 'TMS-L002'),
    ('Hyundai Motors',    '02-4567-8901', 'Daejeon', 'Ulsan',     600, 2.8, 'standard', 'delivered',    5, 'TMS-V001'),
    ('SK Logistics',      '02-5678-9012', 'Gwangju', 'Daejeon',   400, 1.5, 'express',  'delivered',    4, 'TMS-V002'),
    # ── In Transit ─────────────────────────────────────────────────────────
    ('Lotte Distribution','02-6789-0123', 'Seoul',   'Gwangju',  1800, 7.0, 'standard', 'in_transit',   2, 'TMS-L002'),
    ('CJ Logistics',      '02-7890-1234', 'Busan',   'Jeonju',    950, 3.8, 'express',  'in_transit',   1, 'TMS-M002'),
    ('Hanjin Shipping',   '02-8901-2345', 'Incheon', 'Pohang',   3200,14.0, 'urgent',   'in_transit',   1, 'TMS-R001'),
    # ── Dispatched ─────────────────────────────────────────────────────────
    ('Posco Trading',     '02-9012-3456', 'Daegu',   'Cheongju',  750, 3.0, 'standard', 'dispatched',   0, 'TMS-MC01'),
    ('Kakao Commerce',    '02-0123-4567', 'Suwon',   'Goyang',    250, 1.0, 'express',  'dispatched',   0, 'TMS-V002'),
    # ── Pending ────────────────────────────────────────────────────────────
    ('Naver Store',       '031-234-5678', 'Seoul',   'Busan',    1500, 6.0, 'urgent',   'pending',      0, None),
    ('Coupang Logistics', '031-345-6789', 'Incheon', 'Daejeon',   700, 2.5, 'express',  'pending',      0, None),
    ('Gmarket Supply',    '031-456-7890', 'Daejeon', 'Gwangju',   300, 1.2, 'standard', 'pending',      0, None),
    ('Amazon Korea',      '032-567-8901', 'Seoul',   'Ulsan',     900, 3.5, 'express',  'pending',      0, None),
    ('Emart Logistics',   '032-678-9012', 'Busan',   'Daejeon',  1100, 4.2, 'standard', 'pending',      0, None),
]

# Multi-stop shipments: (shipment index 0-based, [(city, stop_type), ...])
MULTI_STOPS = {
    6: [('Changwon', 'waypoint')],                             # Busan→Changwon→Jeonju
    7: [('Daejeon', 'waypoint'), ('Daegu', 'waypoint')],       # Incheon→Daejeon→Daegu→Pohang
}


def _haversine(lat1, lng1, lat2, lng2):
    R = 6371
    f1, f2 = math.radians(lat1), math.radians(lat2)
    a = math.sin(math.radians(lat2 - lat1) / 2) ** 2 + \
        math.cos(f1) * math.cos(f2) * math.sin(math.radians(lng2 - lng1) / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _route_dist(stops):
    total = 0
    for i in range(len(stops) - 1):
        total += _haversine(stops[i][0], stops[i][1], stops[i+1][0], stops[i+1][1])
    return round(total, 1)


def _freight(dist, weight, volume, priority, vtype='truck_medium'):
    rate = {'truck_large': 3.0, 'truck_medium': 2.5, 'van': 1.8,
            'motorcycle': 0.8, 'refrigerated': 3.5}.get(vtype, 2.5)
    base = dist * rate
    w_sur = max(0, weight - 100) * 0.02
    v_sur = max(0, volume - 1.0) * 15.0
    mult = {'standard': 1.0, 'express': 1.3, 'urgent': 1.6}.get(priority, 1.0)
    return round((base + w_sur + v_sur) * mult, 2)


def init_sample_data():
    if Vehicle.query.count() > 0:
        return

    random.seed(99)
    now = datetime.utcnow()

    # ── Vehicles ──────────────────────────────────────────────────────────────
    vehicle_map = {}
    for plate, vtype, cap_kg, cap_m3, dname, dphone, vstatus, hcity in VEHICLES:
        hlat, hlng, _ = CITIES[hcity]
        v = Vehicle(plate=plate, type=vtype, capacity_kg=cap_kg, capacity_m3=cap_m3,
                    driver_name=dname, driver_phone=dphone, status=vstatus,
                    home_lat=hlat, home_lng=hlng)
        db.session.add(v)
        vehicle_map[plate] = v
    db.session.flush()

    # ── Shipments ─────────────────────────────────────────────────────────────
    for idx, (cust, phone, orig, dest, wkg, vm3, pri, sts, days_ago, vplate) in enumerate(SHIPMENTS):
        olat, olng, oaddr = CITIES[orig]
        dlat, dlng, daddr = CITIES[dest]
        created = now - timedelta(days=days_ago, hours=random.randint(0, 8))

        # Build stop list for distance calculation
        stop_coords = [(olat, olng)]
        if idx in MULTI_STOPS:
            for city, _ in MULTI_STOPS[idx]:
                clat, clng, _ = CITIES[city]
                stop_coords.append((clat, clng))
        stop_coords.append((dlat, dlng))

        dist = _route_dist(stop_coords)
        vtype = vehicle_map[vplate].type if vplate else 'truck_medium'
        cost = _freight(dist, wkg, vm3, pri, vtype)

        # Estimate delivery: 1 day per ~300 km
        est_days = max(1, round(dist / 300))
        est_delivery = created + timedelta(days=est_days)
        actual_delivery = est_delivery + timedelta(hours=random.randint(-4, 12)) \
            if sts == 'delivered' else None

        num = f'SHP-2024-{idx+1:03d}'
        s = Shipment(
            shipment_number=num, customer_name=cust, customer_phone=phone,
            origin_address=oaddr, origin_lat=olat, origin_lng=olng,
            destination_address=daddr, destination_lat=dlat, destination_lng=dlng,
            weight_kg=wkg, volume_m3=vm3, priority=pri, status=sts,
            freight_cost=cost, distance_km=dist, created_at=created,
            estimated_delivery=est_delivery, actual_delivery=actual_delivery,
        )
        db.session.add(s)
        db.session.flush()

        # Intermediate stops
        if idx in MULTI_STOPS:
            for order, (city, stype) in enumerate(MULTI_STOPS[idx]):
                clat, clng, caddr = CITIES[city]
                db.session.add(ShipmentStop(
                    shipment_id=s.id, address=caddr, lat=clat, lng=clng,
                    stop_order=order + 1, stop_type=stype
                ))

        # Dispatch
        if vplate and sts in ('dispatched', 'in_transit', 'delivered'):
            d = Dispatch(shipment_id=s.id, vehicle_id=vehicle_map[vplate].id,
                         assigned_at=created + timedelta(hours=2))
            db.session.add(d)

        # Tracking events
        _add_tracking_events(s, created, now)

    db.session.commit()


def _add_tracking_events(s, created, now):
    events = []

    def add(offset_h, etype, desc, city=None):
        lat, lng, addr = CITIES[city] if city else (None, None, None)
        events.append(TrackingEvent(
            shipment_id=s.id, event_type=etype, description=desc,
            location_address=addr, location_lat=lat, location_lng=lng,
            created_at=created + timedelta(hours=offset_h)
        ))

    orig_city = s.origin_address.split(',')[0]
    dest_city = s.destination_address.split(',')[0]

    add(0, 'created', f'Shipment {s.shipment_number} created and queued for dispatch.', orig_city)

    if s.status in ('dispatched', 'in_transit', 'delivered'):
        add(2, 'dispatched', f'Vehicle assigned. Driver en route to pickup.', orig_city)

    if s.status in ('in_transit', 'delivered'):
        add(6, 'picked_up', f'Cargo picked up from {orig_city}.', orig_city)
        # Intermediate checkpoints
        for stop in s.stops:
            city = stop.address.split(',')[0]
            add(12, 'checkpoint', f'Checkpoint cleared at {city}.', city)
        add(18, 'in_transit', f'Shipment in transit toward {dest_city}.', orig_city)

    if s.status == 'delivered':
        add(22, 'out_for_delivery', f'Out for final delivery in {dest_city}.', dest_city)
        add(26, 'delivered', f'Successfully delivered to {s.customer_name} in {dest_city}.', dest_city)

    for e in events:
        db.session.add(e)
