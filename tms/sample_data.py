from models import db, Vehicle, Shipment, ShipmentStop, Dispatch, TrackingEvent, Driver, MaintenanceRecord
from datetime import datetime, timedelta
import math, random

# ── Korean city coordinates ───────────────────────────────────────────────────
CITIES = {
    '서울':    (37.5665, 126.9780, '서울특별시'),
    '부산':    (35.1796, 129.0756, '부산광역시'),
    '대구':    (35.8714, 128.6014, '대구광역시'),
    '인천':    (37.4563, 126.7052, '인천광역시'),
    '광주':    (35.1595, 126.8526, '광주광역시'),
    '대전':    (36.3504, 127.3845, '대전광역시'),
    '울산':    (35.5384, 129.3114, '울산광역시'),
    '수원':    (37.2636, 127.0286, '경기도 수원시'),
    '창원':    (35.2280, 128.6811, '경남 창원시'),
    '고양':    (37.6564, 126.8350, '경기도 고양시'),
    '전주':    (35.8242, 127.1480, '전북 전주시'),
    '청주':    (36.6424, 127.4890, '충북 청주시'),
    '포항':    (36.0190, 129.3435, '경북 포항시'),
    '안산':    (37.3219, 126.8309, '경기도 안산시'),
    '평택':    (36.9921, 127.1127, '경기도 평택시'),
}

# ── Vehicle definitions ───────────────────────────────────────────────────────
# plate, type, cap_kg, cap_m3, driver_name, driver_phone, status, home_city, fuel_eff, mileage
VEHICLES = [
    ('TMS-L001', 'truck_large',  15000, 60.0, '김대한', '010-1234-5678', 'available',   '서울', 8.5,  85000),
    ('TMS-L002', 'truck_large',  15000, 60.0, '이지훈', '010-2345-6789', 'on_route',    '부산', 9.0,  78000),
    ('TMS-M001', 'truck_medium',  5000, 25.0, '박수지', '010-3456-7890', 'available',   '대구', 11.5, 62000),
    ('TMS-M002', 'truck_medium',  5000, 25.0, '최민서', '010-4567-8901', 'on_route',    '대전', 11.0, 45000),
    ('TMS-V001', 'van',           1500,  8.0, '정유나', '010-5678-9012', 'available',   '인천', 14.5, 38000),
    ('TMS-V002', 'van',           1500,  8.0, '한준호', '010-6789-0123', 'available',   '수원', 15.0, 52000),
    ('TMS-V003', 'van',           1500,  8.0, '임소연', '010-7890-1234', 'maintenance', '광주', 13.5, 29000),
    ('TMS-R001', 'refrigerated',  8000, 35.0, '윤석진', '010-8901-2345', 'on_route',    '울산', 7.5,  95000),
    ('TMS-MC01', 'motorcycle',     100,  0.5, '강혜진', '010-9012-3456', 'available',   '고양', 32.0, 18000),
    ('TMS-MC02', 'motorcycle',     100,  0.5, '신동우', '010-0123-4567', 'available',   '안산', 30.0, 12000),
]

# ── Driver definitions ────────────────────────────────────────────────────────
# name, license_num, license_class, phone, email, vehicle_plate, working_hours, total_del, on_time_del, status
DRIVERS = [
    ('김대한', 'KR-DL-2019-001', '1종 대형', '010-1234-5678', 'kim.daehan@logitms.kr',   'TMS-L001', 7.5,  245, 228, 'active'),
    ('이지훈', 'KR-DL-2020-002', '1종 대형', '010-2345-6789', 'lee.jihoon@logitms.kr',   'TMS-L002', 9.2,  198, 176, 'active'),   # over hours!
    ('박수지', 'KR-DL-2018-003', '1종 보통', '010-3456-7890', 'park.suji@logitms.kr',    'TMS-M001', 6.0,  312, 299, 'active'),
    ('최민서', 'KR-DL-2021-004', '1종 보통', '010-4567-8901', 'choi.minseo@logitms.kr',  'TMS-M002', 5.5,  156, 140, 'active'),
    ('정유나', 'KR-DL-2022-005', '1종 보통', '010-5678-9012', 'jung.yuna@logitms.kr',    'TMS-V001', 4.0,   89,  82, 'active'),
    ('한준호', 'KR-DL-2017-006', '1종 보통', '010-6789-0123', 'han.junho@logitms.kr',    'TMS-V002', 8.5,  445, 420, 'active'),
    ('임소연', 'KR-DL-2023-007', '1종 보통', '010-7890-1234', 'im.soyeon@logitms.kr',    'TMS-V003', 0.0,   34,  30, 'off_duty'),
    ('윤석진', 'KR-DL-2016-008', '1종 대형', '010-8901-2345', 'yoon.seokjin@logitms.kr', 'TMS-R001', 7.0,  520, 489, 'active'),
    ('강혜진', 'KR-DL-2022-009', '2종 보통', '010-9012-3456', 'kang.hyejin@logitms.kr',  'TMS-MC01', 3.5,   67,  60, 'active'),
    ('신동우', 'KR-DL-2023-010', '2종 보통', '010-0123-4567', 'shin.dongwoo@logitms.kr', 'TMS-MC02', 2.0,   45,  40, 'active'),
]

# ── Maintenance records ───────────────────────────────────────────────────────
# plate, type, sched_days_from_now, done_days_from_now (None=not done), cost, status, mileage
MAINTENANCE = [
    ('TMS-L001', '정기 점검',        -30, -28, 250_000, 'completed', 84000),
    ('TMS-L001', '타이어 교체',        14, None, 320_000, 'scheduled', 92000),
    ('TMS-L002', '엔진 오일 교체',     -5,  -3,  45_000, 'completed', 77000),
    ('TMS-L002', '브레이크 패드',       7, None, 180_000, 'scheduled', 80000),
    ('TMS-M001', '정기 점검',          -60, -58, 200_000, 'completed', 61000),
    ('TMS-M001', '에어컨 점검',         21, None,  85_000, 'scheduled', 65000),
    ('TMS-M002', '배터리 교체',         -2, None, 150_000, 'overdue',   44000),
    ('TMS-V001', '타이어 교체',        -10,  -8, 280_000, 'completed', 37000),
    ('TMS-V002', '엔진 오일 교체',       5, None,  45_000, 'scheduled', 52000),
    ('TMS-V003', '정기 점검',           -1, None, 200_000, 'overdue',   29000),
    ('TMS-R001', '냉동장치 점검',      -15, -13, 350_000, 'completed', 94000),
    ('TMS-R001', '정기 점검',           30, None, 250_000, 'scheduled', 98000),
    ('TMS-MC01', '타이어 교체',         10, None,  60_000, 'scheduled', 18000),
    ('TMS-MC02', '엔진 오일 교체',      -3, None,  25_000, 'overdue',   12000),
]

# ── Shipment definitions ──────────────────────────────────────────────────────
# customer, phone, orig, dest, weight_kg, vol_m3, priority, status, days_ago, vehicle_plate
SHIPMENTS = [
    # Delivered
    ('테크코프 코리아',    '02-1234-5678', '서울', '부산',  1200, 4.5, 'express',  'delivered',  10, 'TMS-L001'),
    ('삼성 파트너스',     '02-2345-6789', '인천', '대구',   800, 3.2, 'standard', 'delivered',   8, 'TMS-M001'),
    ('LG 전자',          '02-3456-7890', '부산', '서울',  2500,10.0, 'urgent',   'delivered',   6, 'TMS-L002'),
    ('현대자동차',        '02-4567-8901', '대전', '울산',   600, 2.8, 'standard', 'delivered',   5, 'TMS-V001'),
    ('SK 로지스틱스',     '02-5678-9012', '광주', '대전',   400, 1.5, 'express',  'delivered',   4, 'TMS-V002'),
    ('쿠팡 로지스틱스',   '031-345-6789', '서울', '수원',   350, 1.2, 'express',  'delivered',   3, 'TMS-MC01'),
    ('롯데 유통',         '02-7890-1234', '대구', '전주',   950, 3.8, 'standard', 'delivered',   7, 'TMS-M002'),
    ('CJ 대한통운',       '02-8901-2345', '부산', '청주',  1100, 4.2, 'express',  'delivered',   9, 'TMS-L001'),
    # In Transit
    ('롯데 물류',         '02-6789-0123', '서울', '광주',  1800, 7.0, 'standard', 'in_transit',  2, 'TMS-L002'),
    ('CJ 로지스틱스',     '02-7890-1234', '부산', '전주',   950, 3.8, 'express',  'in_transit',  1, 'TMS-M002'),
    ('한진 해운',         '02-8901-2345', '인천', '포항',  3200,14.0, 'urgent',   'in_transit',  1, 'TMS-R001'),
    # Dispatched
    ('포스코 트레이딩',   '02-9012-3456', '대구', '청주',   750, 3.0, 'standard', 'dispatched',  0, 'TMS-MC01'),
    ('카카오 커머스',     '02-0123-4567', '수원', '고양',   250, 1.0, 'express',  'dispatched',  0, 'TMS-V002'),
    # Pending
    ('네이버 스토어',     '031-234-5678', '서울', '부산',  1500, 6.0, 'urgent',   'pending',     0, None),
    ('쿠팡 물류',         '031-345-6789', '인천', '대전',   700, 2.5, 'express',  'pending',     0, None),
    ('G마켓 공급',        '031-456-7890', '대전', '광주',   300, 1.2, 'standard', 'pending',     0, None),
    ('아마존 코리아',     '032-567-8901', '서울', '울산',   900, 3.5, 'express',  'pending',     0, None),
    ('이마트 물류',       '032-678-9012', '부산', '대전',  1100, 4.2, 'standard', 'pending',     0, None),
]

# Multi-stop shipments: {shipment_index: [(city, stop_type), ...]}
MULTI_STOPS = {
    9:  [('창원', 'waypoint')],                                     # 부산→창원→전주
    10: [('대전', 'waypoint'), ('대구', 'waypoint')],               # 인천→대전→대구→포항
    13: [('대전', 'waypoint'), ('대구', 'waypoint'), ('울산', 'waypoint')],  # 서울→(3경유)→부산
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
    for plate, vtype, cap_kg, cap_m3, dname, dphone, vstatus, hcity, fuel_eff, mileage in VEHICLES:
        hlat, hlng, _ = CITIES[hcity]
        v = Vehicle(plate=plate, type=vtype, capacity_kg=cap_kg, capacity_m3=cap_m3,
                    driver_name=dname, driver_phone=dphone, status=vstatus,
                    home_lat=hlat, home_lng=hlng,
                    fuel_efficiency_kmpl=fuel_eff, mileage_km=mileage)
        db.session.add(v)
        vehicle_map[plate] = v
    db.session.flush()

    # ── Drivers ───────────────────────────────────────────────────────────────
    for dname, lic_num, lic_cls, phone, email, vplate, wh, total, on_time, dstatus in DRIVERS:
        v = vehicle_map.get(vplate)
        d = Driver(name=dname, license_number=lic_num, license_class=lic_cls,
                   phone=phone, email=email,
                   vehicle_id=v.id if v else None,
                   working_hours_today=wh, total_deliveries=total,
                   on_time_deliveries=on_time, status=dstatus)
        db.session.add(d)
    db.session.flush()

    # ── Maintenance records ────────────────────────────────────────────────────
    for plate, mtype, sched_d, done_d, cost, mstatus, mileage in MAINTENANCE:
        v = vehicle_map.get(plate)
        if not v:
            continue
        sched = now + timedelta(days=sched_d)
        done  = (now + timedelta(days=done_d)) if done_d is not None else None
        db.session.add(MaintenanceRecord(
            vehicle_id=v.id, maintenance_type=mtype,
            scheduled_date=sched, completed_date=done,
            cost=cost, status=mstatus, mileage_km=mileage
        ))
    db.session.flush()

    # ── Shipments ─────────────────────────────────────────────────────────────
    for idx, (cust, phone, orig, dest, wkg, vm3, pri, sts, days_ago, vplate) in enumerate(SHIPMENTS):
        olat, olng, oaddr = CITIES[orig]
        dlat, dlng, daddr = CITIES[dest]
        created = now - timedelta(days=days_ago, hours=random.randint(0, 8))

        stop_coords = [(olat, olng)]
        if idx in MULTI_STOPS:
            for city, _ in MULTI_STOPS[idx]:
                clat, clng, _ = CITIES[city]
                stop_coords.append((clat, clng))
        stop_coords.append((dlat, dlng))

        dist = _route_dist(stop_coords)
        vtype = vehicle_map[vplate].type if vplate else 'truck_medium'
        cost = _freight(dist, wkg, vm3, pri, vtype)

        est_days = max(1, round(dist / 300))
        est_delivery = created + timedelta(days=est_days)

        if sts == 'delivered':
            # Mix on-time (80%) and late (20%)
            if random.random() < 0.8:
                actual_delivery = est_delivery - timedelta(hours=random.randint(0, 4))
            else:
                actual_delivery = est_delivery + timedelta(hours=random.randint(1, 12))
        else:
            actual_delivery = None

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

        if idx in MULTI_STOPS:
            for order, (city, stype) in enumerate(MULTI_STOPS[idx]):
                clat, clng, caddr = CITIES[city]
                db.session.add(ShipmentStop(
                    shipment_id=s.id, address=caddr, lat=clat, lng=clng,
                    stop_order=order + 1, stop_type=stype
                ))

        if vplate and sts in ('dispatched', 'in_transit', 'delivered'):
            dispatch_time = created + timedelta(hours=2)
            db.session.add(Dispatch(
                shipment_id=s.id,
                vehicle_id=vehicle_map[vplate].id,
                assigned_at=dispatch_time
            ))

        _add_tracking_events(s, created, now)

    db.session.commit()


def _add_tracking_events(s, created, now):
    events = []

    def add(offset_h, etype, desc, city=None):
        if city and city in CITIES:
            lat, lng, addr = CITIES[city]
        else:
            lat, lng, addr = None, None, None
        events.append(TrackingEvent(
            shipment_id=s.id, event_type=etype, description=desc,
            location_address=addr, location_lat=lat, location_lng=lng,
            created_at=created + timedelta(hours=offset_h)
        ))

    orig_city = list(CITIES.keys())[
        next((i for i, (la, lo, a) in enumerate(CITIES.values())
              if abs(la - s.origin_lat) < 0.01), 0)
    ]
    dest_city = list(CITIES.keys())[
        next((i for i, (la, lo, a) in enumerate(CITIES.values())
              if abs(la - s.destination_lat) < 0.01), 0)
    ]

    add(0, 'created', f'화물 {s.shipment_number} 접수 완료. 배차 대기 중.')

    if s.status in ('dispatched', 'in_transit', 'delivered'):
        add(2, 'dispatched', f'차량 배정 완료. 기사가 상차 장소로 이동 중.')

    if s.status in ('in_transit', 'delivered'):
        add(6, 'picked_up', f'{orig_city}에서 화물 상차 완료.')
        for stop in s.stops:
            city = stop.address.split(' ')[0] if stop.address else ''
            add(12, 'checkpoint', f'{city} 경유지 통과.')
        add(18, 'in_transit', f'{dest_city} 방면 운송 중.')

    if s.status == 'delivered':
        add(22, 'out_for_delivery', f'{dest_city} 배달 출발.')
        add(26, 'delivered', f'{s.customer_name}에게 배달 완료.')

    for e in events:
        db.session.add(e)
