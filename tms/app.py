from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from models import db, Vehicle, Shipment, ShipmentStop, Dispatch, TrackingEvent, Driver, MaintenanceRecord
from datetime import datetime, timedelta
from collections import defaultdict
import json, math

app = Flask(__name__)
app.config['SECRET_KEY'] = 'tms-dev-secret-2024'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///tms.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

FUEL_PRICE_KRW = 1650   # diesel price per liter
SPEED_KMH      = 80     # average vehicle speed
TIME_COMPRESSION = 30   # 1 real second = 30 simulated seconds (for tracking demo)


# ── Geo helpers ───────────────────────────────────────────────────────────────
def haversine(lat1, lng1, lat2, lng2):
    R = 6371
    f1, f2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin(math.radians(lat2 - lat1) / 2) ** 2 +
         math.cos(f1) * math.cos(f2) * math.sin(math.radians(lng2 - lng1) / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def route_distance(stops):
    total = 0.0
    for i in range(len(stops) - 1):
        s, t = stops[i], stops[i + 1]
        if isinstance(s, dict):
            total += haversine(s['lat'], s['lng'], t['lat'], t['lng'])
        else:
            total += haversine(s[0], s[1], t[0], t[1])
    return round(total, 1)


def interpolate_position(route, elapsed_km):
    """Interpolate vehicle position given elapsed distance along route."""
    cum = 0.0
    for i in range(len(route) - 1):
        seg = haversine(route[i]['lat'], route[i]['lng'],
                        route[i + 1]['lat'], route[i + 1]['lng'])
        if cum + seg >= elapsed_km:
            t = (elapsed_km - cum) / seg if seg > 0 else 0
            lat = route[i]['lat'] + (route[i + 1]['lat'] - route[i]['lat']) * t
            lng = route[i]['lng'] + (route[i + 1]['lng'] - route[i]['lng']) * t
            return lat, lng, i
        cum += seg
    return route[-1]['lat'], route[-1]['lng'], len(route) - 1


# ── Route optimization ────────────────────────────────────────────────────────
def nearest_neighbor_optimize(stops):
    if len(stops) <= 2:
        return stops, False
    start, end, middle = stops[0], stops[-1], stops[1:-1]
    if not middle:
        return stops, False
    optimized, unvisited, current = [], middle[:], start
    while unvisited:
        nearest = min(unvisited, key=lambda s: haversine(
            current['lat'], current['lng'], s['lat'], s['lng']))
        optimized.append(nearest)
        unvisited.remove(nearest)
        current = nearest
    new_stops = [start] + optimized + [end]
    return new_stops, [s.get('address') for s in stops] != [s.get('address') for s in new_stops]


def two_opt_optimize(stops):
    """2-opt local search improvement."""
    if len(stops) <= 3:
        return stops, False
    start, end = stops[0], stops[-1]
    best = stops[1:-1][:]
    best_dist = route_distance([start] + best + [end])
    improved = True
    while improved:
        improved = False
        for i in range(len(best)):
            for j in range(i + 2, len(best) + 1):
                candidate = best[:i] + best[i:j][::-1] + best[j:]
                d = route_distance([start] + candidate + [end])
                if d < best_dist - 0.001:
                    best, best_dist, improved = candidate, d, True
                    break
            if improved:
                break
    new_stops = [start] + best + [end]
    return new_stops, best_dist < route_distance(stops) - 0.001


def estimate_freight(distance_km, weight_kg, volume_m3, priority, vehicle_type='truck_medium'):
    rate  = {'truck_large': 3.0, 'truck_medium': 2.5, 'van': 1.8,
             'motorcycle': 0.8, 'refrigerated': 3.5}.get(vehicle_type, 2.5)
    base  = distance_km * rate
    w_sur = max(0, weight_kg - 100) * 0.02
    v_sur = max(0, volume_m3 - 1.0) * 15.0
    mult  = {'standard': 1.0, 'express': 1.3, 'urgent': 1.6}.get(priority, 1.0)
    return round((base + w_sur + v_sur) * mult, 2)


# ── Dashboard ─────────────────────────────────────────────────────────────────
@app.route('/')
def dashboard():
    all_shipments   = Shipment.query.all()
    total           = len(all_shipments)
    in_transit      = sum(1 for s in all_shipments if s.status == 'in_transit')
    delivered_today = sum(1 for s in all_shipments
                          if s.status == 'delivered' and s.actual_delivery and
                          s.actual_delivery.date() == datetime.utcnow().date())
    pending         = sum(1 for s in all_shipments if s.status == 'pending')
    avail_vehicles  = Vehicle.query.filter_by(status='available').count()
    over_hours_drivers = Driver.query.filter(Driver.working_hours_today > 8.0).count()
    pending_maintenance = MaintenanceRecord.query.filter_by(status='overdue').count()

    features = []
    for s in all_shipments:
        if s.status == 'cancelled':
            continue
        color = {'pending': '#94a3b8', 'dispatched': '#06b6d4',
                 'in_transit': '#3b82f6', 'delivered': '#22c55e'}.get(s.status, '#94a3b8')
        features.append({
            'type': 'Feature',
            'geometry': {'type': 'Point', 'coordinates': [s.origin_lng, s.origin_lat]},
            'properties': {
                'number': s.shipment_number, 'customer': s.customer_name,
                'status': s.status, 'origin': s.origin_address,
                'dest': s.destination_address, 'color': color, 'id': s.id,
                'route': [[s.origin_lat, s.origin_lng]] +
                         [[st.lat, st.lng] for st in s.stops] +
                         [[s.destination_lat, s.destination_lng]],
            }
        })

    status_counts = defaultdict(int)
    for s in all_shipments:
        status_counts[s.status] += 1

    monthly = defaultdict(int)
    for s in all_shipments:
        monthly[s.created_at.strftime('%b %Y')] += 1
    months_sorted = sorted(monthly.keys(), key=lambda x: datetime.strptime(x, '%b %Y'))[-6:]
    monthly_data = [{'month': m, 'count': monthly[m]} for m in months_sorted]

    recent = Shipment.query.order_by(Shipment.created_at.desc()).limit(8).all()

    return render_template('dashboard.html',
                           total=total, in_transit=in_transit,
                           delivered_today=delivered_today, pending=pending,
                           avail_vehicles=avail_vehicles,
                           over_hours_drivers=over_hours_drivers,
                           pending_maintenance=pending_maintenance,
                           geojson=json.dumps({'type': 'FeatureCollection', 'features': features}),
                           status_counts=json.dumps(dict(status_counts)),
                           monthly_json=json.dumps(monthly_data),
                           recent=recent)


# ── Real-Time Tracking ────────────────────────────────────────────────────────
@app.route('/tracking/<int:sid>')
def tracking(sid):
    s = Shipment.query.get_or_404(sid)
    route = s.all_stops()
    return render_template('tracking.html', s=s, route=json.dumps(route))


@app.route('/api/tracking-position/<int:sid>')
def api_tracking_position(sid):
    s = Shipment.query.get_or_404(sid)
    route = s.all_stops()
    total_dist = route_distance(route)

    if s.status == 'delivered':
        return jsonify({
            'lat': s.destination_lat, 'lng': s.destination_lng,
            'progress': 100, 'elapsed_km': total_dist, 'total_km': total_dist,
            'remaining_km': 0, 'eta_minutes': 0, 'status': 'delivered',
            'current_location': s.destination_address,
            'segment': len(route) - 1,
            'route': [[r['lat'], r['lng']] for r in route],
            'vehicle': _vehicle_info(s),
        })

    if s.status not in ('dispatched', 'in_transit'):
        return jsonify({'status': s.status, 'progress': 0,
                        'route': [[r['lat'], r['lng']] for r in route]})

    dispatch_time = s.dispatch.assigned_at if s.dispatch else s.created_at
    elapsed_s     = (datetime.utcnow() - dispatch_time).total_seconds()

    # Time compression: each real second = TIME_COMPRESSION simulated seconds
    elapsed_km = (elapsed_s * TIME_COMPRESSION / 3600) * SPEED_KMH
    elapsed_km = min(elapsed_km, total_dist)

    lat, lng, seg_idx = interpolate_position(route, elapsed_km)
    progress = round(elapsed_km / total_dist * 100, 1) if total_dist > 0 else 0
    remaining_km = total_dist - elapsed_km
    # ETA in real minutes
    eta_minutes = int(remaining_km / SPEED_KMH / TIME_COMPRESSION * 3600 / 60)

    current_loc = route[seg_idx]['address']
    if seg_idx + 1 < len(route):
        current_loc += f" → {route[seg_idx + 1]['address']}"

    # Determine live status text
    if elapsed_km < 5:
        live_status = 'departing'
    elif elapsed_km >= total_dist * 0.9:
        live_status = 'arriving'
    else:
        live_status = 'in_transit'

    return jsonify({
        'lat': round(lat, 6), 'lng': round(lng, 6),
        'progress': progress,
        'elapsed_km': round(elapsed_km, 1),
        'total_km': round(total_dist, 1),
        'remaining_km': round(remaining_km, 1),
        'eta_minutes': eta_minutes,
        'status': live_status,
        'current_location': current_loc,
        'segment': seg_idx,
        'route': [[r['lat'], r['lng']] for r in route],
        'vehicle': _vehicle_info(s),
    })


def _vehicle_info(s):
    if not s.dispatch:
        return {}
    v = s.dispatch.vehicle
    return {
        'plate': v.plate, 'driver': v.driver_name,
        'type': v.type_display(), 'icon': v.icon(),
        'fuel_cost_per_km': v.fuel_cost_per_km(FUEL_PRICE_KRW),
    }


# ── Shipments ─────────────────────────────────────────────────────────────────
@app.route('/shipments')
def shipments():
    status_f   = request.args.get('status', '')
    priority_f = request.args.get('priority', '')
    search     = request.args.get('q', '')
    q = Shipment.query
    if status_f:   q = q.filter_by(status=status_f)
    if priority_f: q = q.filter_by(priority=priority_f)
    if search:
        q = q.filter(Shipment.shipment_number.ilike(f'%{search}%') |
                     Shipment.customer_name.ilike(f'%{search}%'))
    all_s = q.order_by(Shipment.created_at.desc()).all()
    return render_template('shipments.html', shipments=all_s,
                           status_f=status_f, priority_f=priority_f, search=search)


@app.route('/shipments/new', methods=['GET', 'POST'])
def new_shipment():
    if request.method == 'POST':
        customer_name  = request.form.get('customer_name', '').strip()
        customer_phone = request.form.get('customer_phone', '').strip()
        customer_email = request.form.get('customer_email', '').strip()
        origin_addr    = request.form.get('origin_address', '').strip()
        origin_lat     = request.form.get('origin_lat',  type=float)
        origin_lng     = request.form.get('origin_lng',  type=float)
        dest_addr      = request.form.get('dest_address', '').strip()
        dest_lat       = request.form.get('dest_lat',    type=float)
        dest_lng       = request.form.get('dest_lng',    type=float)
        weight_kg      = request.form.get('weight_kg',   type=float) or 0
        volume_m3      = request.form.get('volume_m3',   type=float) or 0
        priority       = request.form.get('priority', 'standard')
        notes          = request.form.get('notes', '').strip()

        if not all([customer_name, origin_addr, dest_addr, origin_lat, dest_lat]):
            flash('필수 항목을 모두 입력하고 지도에서 위치를 설정하세요.', 'danger')
            return redirect(url_for('new_shipment'))

        dist = haversine(origin_lat, origin_lng, dest_lat, dest_lng)
        cost = estimate_freight(dist, weight_kg, volume_m3, priority)
        est_days = max(1, round(dist / 300))

        count = Shipment.query.count() + 1
        num   = f'SHP-{datetime.utcnow().strftime("%Y")}-{count:03d}'
        s = Shipment(
            shipment_number=num, customer_name=customer_name,
            customer_phone=customer_phone, customer_email=customer_email,
            origin_address=origin_addr, origin_lat=origin_lat, origin_lng=origin_lng,
            destination_address=dest_addr, destination_lat=dest_lat, destination_lng=dest_lng,
            weight_kg=weight_kg, volume_m3=volume_m3, priority=priority,
            freight_cost=cost, distance_km=round(dist, 1), notes=notes,
            estimated_delivery=datetime.utcnow() + timedelta(days=est_days)
        )
        db.session.add(s)
        db.session.flush()
        db.session.add(TrackingEvent(
            shipment_id=s.id, event_type='created',
            description=f'화물 {num} 접수 완료.',
            location_address=origin_addr, location_lat=origin_lat, location_lng=origin_lng
        ))
        db.session.commit()
        flash(f'화물 {num} 등록 완료. 예상 운임: ₩{cost:,.0f}', 'success')
        return redirect(url_for('shipment_detail', sid=s.id))

    return render_template('shipment_new.html')


@app.route('/shipments/<int:sid>')
def shipment_detail(sid):
    s = Shipment.query.get_or_404(sid)
    route = s.all_stops()
    return render_template('shipment_detail.html', s=s, route=json.dumps(route))


@app.route('/shipments/<int:sid>/update_status', methods=['POST'])
def update_status(sid):
    s      = Shipment.query.get_or_404(sid)
    new_st = request.form.get('status')
    note   = request.form.get('note', '').strip()
    valid  = ('pending', 'dispatched', 'in_transit', 'delivered', 'cancelled')

    if new_st not in valid:
        flash('잘못된 상태값입니다.', 'danger')
        return redirect(url_for('shipment_detail', sid=sid))

    s.status = new_st
    if new_st == 'delivered':
        s.actual_delivery = datetime.utcnow()
        if s.dispatch and s.dispatch.vehicle:
            s.dispatch.vehicle.status = 'available'

    evt_map = {
        'dispatched': ('dispatched',    '차량 배정 완료. 상차 이동 중.'),
        'in_transit': ('picked_up',     '화물 상차 완료. 운송 개시.'),
        'delivered':  ('delivered',     f'{s.customer_name}에게 배달 완료.'),
        'cancelled':  ('cancelled',     '화물 취소 처리.'),
    }
    if new_st in evt_map:
        etype, edesc = evt_map[new_st]
        db.session.add(TrackingEvent(
            shipment_id=s.id, event_type=etype, description=note or edesc,
            location_address=s.origin_address,
            location_lat=s.origin_lat, location_lng=s.origin_lng
        ))

    db.session.commit()
    flash(f'상태 변경 완료.', 'success')
    return redirect(url_for('shipment_detail', sid=sid))


# ── Dispatch ──────────────────────────────────────────────────────────────────
@app.route('/dispatch')
def dispatch():
    pending_shipments  = Shipment.query.filter_by(status='pending').order_by(Shipment.created_at).all()
    available_vehicles = Vehicle.query.filter_by(status='available').all()
    active_dispatches  = (Dispatch.query.join(Shipment)
                          .filter(Shipment.status.in_(['dispatched', 'in_transit']))
                          .order_by(Dispatch.assigned_at.desc()).all())
    return render_template('dispatch.html',
                           pending_shipments=pending_shipments,
                           available_vehicles=available_vehicles,
                           active_dispatches=active_dispatches)


@app.route('/dispatch/assign', methods=['POST'])
def assign_vehicle():
    sid    = request.form.get('shipment_id', type=int)
    vid    = request.form.get('vehicle_id',  type=int)
    dnotes = request.form.get('driver_notes', '').strip()
    s = Shipment.query.get_or_404(sid)
    v = Vehicle.query.get_or_404(vid)

    if s.dispatch:
        flash(f'{s.shipment_number}는 이미 배차됐습니다.', 'warning')
        return redirect(url_for('dispatch'))
    if v.status != 'available':
        flash(f'{v.plate} 차량은 현재 사용 불가 상태입니다.', 'danger')
        return redirect(url_for('dispatch'))
    if s.weight_kg > v.capacity_kg:
        flash(f'중량 초과: {s.weight_kg}kg > 차량 적재량 {v.capacity_kg}kg', 'danger')
        return redirect(url_for('dispatch'))

    db.session.add(Dispatch(shipment_id=sid, vehicle_id=vid, driver_notes=dnotes))
    s.status  = 'dispatched'
    v.status  = 'on_route'
    s.freight_cost = estimate_freight(s.distance_km or 0, s.weight_kg,
                                      s.volume_m3, s.priority, v.type)
    db.session.add(TrackingEvent(
        shipment_id=sid, event_type='dispatched',
        description=f'{v.type_display()} {v.plate} 배정 — 기사: {v.driver_name}.',
        location_address=s.origin_address, location_lat=s.origin_lat, location_lng=s.origin_lng
    ))
    db.session.commit()
    flash(f'{v.plate} 차량을 {s.shipment_number}에 배차했습니다.', 'success')
    return redirect(url_for('dispatch'))


# ── Vehicles ──────────────────────────────────────────────────────────────────
@app.route('/vehicles')
def vehicles():
    all_v = Vehicle.query.order_by(Vehicle.type, Vehicle.plate).all()
    avail = sum(1 for v in all_v if v.status == 'available')
    on_rt = sum(1 for v in all_v if v.status == 'on_route')
    maint = sum(1 for v in all_v if v.status == 'maintenance')
    overdue_count = sum(v.overdue_maintenance() for v in all_v)
    upcoming = (MaintenanceRecord.query
                .filter_by(status='scheduled')
                .filter(MaintenanceRecord.scheduled_date <= datetime.utcnow() + timedelta(days=14))
                .order_by(MaintenanceRecord.scheduled_date)
                .all())
    return render_template('vehicles.html', vehicles=all_v,
                           avail=avail, on_rt=on_rt, maint=maint,
                           overdue_count=overdue_count, upcoming=upcoming,
                           now=datetime.utcnow())


@app.route('/vehicles/new', methods=['GET', 'POST'])
def new_vehicle():
    if request.method == 'POST':
        plate     = request.form.get('plate', '').strip().upper()
        vtype     = request.form.get('type', '')
        cap_kg    = request.form.get('capacity_kg', type=float) or 0
        cap_m3    = request.form.get('capacity_m3', type=float) or 0
        dname     = request.form.get('driver_name', '').strip()
        dphone    = request.form.get('driver_phone', '').strip()
        fuel_eff  = request.form.get('fuel_efficiency_kmpl', type=float) or 10.0
        mileage   = request.form.get('mileage_km', type=int) or 0
        notes     = request.form.get('notes', '').strip()

        if not plate or not vtype:
            flash('차량 번호판과 유형은 필수입니다.', 'danger')
            return redirect(url_for('new_vehicle'))
        if Vehicle.query.filter_by(plate=plate).first():
            flash(f'번호판 {plate}이 이미 존재합니다.', 'danger')
            return redirect(url_for('new_vehicle'))

        v = Vehicle(plate=plate, type=vtype, capacity_kg=cap_kg, capacity_m3=cap_m3,
                    driver_name=dname, driver_phone=dphone,
                    fuel_efficiency_kmpl=fuel_eff, mileage_km=mileage, notes=notes)
        db.session.add(v)
        db.session.commit()
        flash(f'차량 {plate} 등록 완료.', 'success')
        return redirect(url_for('vehicles'))

    return render_template('vehicle_new.html')


@app.route('/vehicles/<int:vid>/status', methods=['POST'])
def update_vehicle_status(vid):
    v = Vehicle.query.get_or_404(vid)
    new_st = request.form.get('status')
    if new_st in ('available', 'on_route', 'maintenance'):
        v.status = new_st
        db.session.commit()
        flash(f'{v.plate} 상태 변경 완료.', 'success')
    return redirect(url_for('vehicles'))


@app.route('/vehicles/<int:vid>/maintenance/add', methods=['POST'])
def add_maintenance(vid):
    v = Vehicle.query.get_or_404(vid)
    mtype      = request.form.get('maintenance_type', '').strip()
    sched_days = request.form.get('scheduled_days', type=int) or 7
    cost       = request.form.get('cost', type=int) or 0
    notes      = request.form.get('notes', '').strip()
    db.session.add(MaintenanceRecord(
        vehicle_id=vid,
        maintenance_type=mtype,
        scheduled_date=datetime.utcnow() + timedelta(days=sched_days),
        cost=cost, notes=notes, status='scheduled',
        mileage_km=v.mileage_km
    ))
    db.session.commit()
    flash(f'{v.plate} 정비 일정이 등록됐습니다.', 'success')
    return redirect(url_for('vehicles'))


# ── Drivers ───────────────────────────────────────────────────────────────────
@app.route('/drivers')
def drivers():
    all_drivers = Driver.query.order_by(Driver.name).all()
    over_hours  = [d for d in all_drivers if d.is_over_hours()]
    # Ranking by performance score
    ranked = sorted(all_drivers, key=lambda d: d.performance_score(), reverse=True)
    return render_template('drivers.html', drivers=all_drivers,
                           over_hours=over_hours, ranked=ranked)


@app.route('/drivers/<int:did>')
def driver_detail(did):
    d = Driver.query.get_or_404(did)
    # Recent shipments via vehicle
    recent_shipments = []
    if d.vehicle:
        recent_shipments = (Dispatch.query.filter_by(vehicle_id=d.vehicle.id)
                            .join(Shipment)
                            .order_by(Dispatch.assigned_at.desc())
                            .limit(10).all())
    return render_template('driver_detail.html', driver=d, recent_shipments=recent_shipments)


# ── Route Optimization ────────────────────────────────────────────────────────
@app.route('/routes')
def routes_view():
    active = Shipment.query.filter(Shipment.status.in_(['dispatched', 'in_transit'])).all()

    routes_geo = []
    for s in active:
        coords = [[s.origin_lat, s.origin_lng]]
        for st in s.stops:
            coords.append([st.lat, st.lng])
        coords.append([s.destination_lat, s.destination_lng])
        color = '#3b82f6' if s.status == 'in_transit' else '#06b6d4'
        routes_geo.append({
            'id': s.id, 'number': s.shipment_number, 'customer': s.customer_name,
            'status': s.status, 'coords': coords, 'color': color,
            'origin': s.origin_address, 'dest': s.destination_address,
        })

    multi_stop = [s for s in
                  Shipment.query.filter(Shipment.status.in_(['pending', 'dispatched', 'in_transit'])).all()
                  if len(s.stops) >= 1]

    selected_id = request.args.get('optimize', type=int)
    opt_result  = None
    if selected_id:
        s = Shipment.query.get(selected_id)
        if s:
            all_st    = s.all_stops()
            orig_dist = route_distance(all_st)

            nn_stops,  nn_changed  = nearest_neighbor_optimize(all_st)
            opt2_stops, opt2_changed = two_opt_optimize(all_st)
            nn_dist   = route_distance(nn_stops)
            opt2_dist = route_distance(opt2_stops)

            avg_speed = SPEED_KMH
            rate_per_km = 2500  # KRW per km (approx)

            opt_result = {
                'shipment':    s,
                'original':    all_st,
                'nn_stops':    nn_stops,
                'opt2_stops':  opt2_stops,
                'orig_dist':   orig_dist,
                'nn_dist':     nn_dist,
                'opt2_dist':   opt2_dist,
                'nn_saved_km': round(orig_dist - nn_dist, 1),
                'opt2_saved_km': round(orig_dist - opt2_dist, 1),
                'nn_saved_min': round((orig_dist - nn_dist) / avg_speed * 60),
                'opt2_saved_min': round((orig_dist - opt2_dist) / avg_speed * 60),
                'nn_saved_krw': round((orig_dist - nn_dist) * rate_per_km / 1000) * 1000,
                'opt2_saved_krw': round((orig_dist - opt2_dist) * rate_per_km / 1000) * 1000,
                'nn_changed':  nn_changed,
                'opt2_changed': opt2_changed,
            }

    return render_template('routes.html',
                           routes_geo=json.dumps(routes_geo),
                           multi_stop=multi_stop,
                           opt_result=opt_result,
                           selected_id=selected_id)


@app.route('/api/optimize', methods=['POST'])
def api_optimize():
    data  = request.get_json()
    stops = data.get('stops', [])
    if len(stops) < 3:
        return jsonify({'error': '최소 3개 이상의 경유지가 필요합니다.'}), 400

    orig_dist  = route_distance(stops)
    nn_stops,  _  = nearest_neighbor_optimize(stops)
    opt2_stops, _ = two_opt_optimize(stops)
    nn_dist   = route_distance(nn_stops)
    opt2_dist = route_distance(opt2_stops)

    return jsonify({
        'original_distance': orig_dist,
        'nn': {'stops': nn_stops,   'distance': nn_dist,   'saved': round(orig_dist - nn_dist, 1)},
        'two_opt': {'stops': opt2_stops, 'distance': opt2_dist, 'saved': round(orig_dist - opt2_dist, 1)},
    })


@app.route('/api/freight_estimate')
def api_freight_estimate():
    lat1   = request.args.get('lat1',   type=float)
    lng1   = request.args.get('lng1',   type=float)
    lat2   = request.args.get('lat2',   type=float)
    lng2   = request.args.get('lng2',   type=float)
    weight = request.args.get('weight', type=float) or 0
    volume = request.args.get('volume', type=float) or 0
    pri    = request.args.get('priority', 'standard')
    vtype  = request.args.get('vehicle_type', 'truck_medium')
    if not all([lat1, lng1, lat2, lng2]):
        return jsonify({'error': '좌표가 필요합니다.'}), 400
    dist = haversine(lat1, lng1, lat2, lng2)
    cost = estimate_freight(dist, weight, volume, pri, vtype)
    return jsonify({'distance_km': round(dist, 1), 'freight_cost': cost})


# ── Performance KPI Dashboard ─────────────────────────────────────────────────
@app.route('/performance')
def performance():
    all_s  = Shipment.query.all()
    all_d  = Driver.query.order_by(Driver.name).all()
    delivered = [s for s in all_s if s.status == 'delivered']

    # On-time delivery rate
    on_time = sum(1 for s in delivered
                  if s.actual_delivery and s.estimated_delivery and
                  s.actual_delivery <= s.estimated_delivery)
    on_time_pct = round(on_time / len(delivered) * 100, 1) if delivered else 0

    # SLA compliance by priority
    sla_data = {}
    for pri in ('urgent', 'express', 'standard'):
        sla_hours = {'urgent': 24, 'express': 36, 'standard': 72}[pri]
        pri_del = [s for s in delivered if s.priority == pri]
        compliant = sum(1 for s in pri_del
                        if s.actual_delivery and
                        s.actual_delivery <= s.created_at + timedelta(hours=sla_hours))
        sla_data[pri] = {
            'total': len(pri_del),
            'compliant': compliant,
            'rate': round(compliant / len(pri_del) * 100, 1) if pri_del else 0,
        }

    # Average delivery time by destination region
    region_times = defaultdict(list)
    for s in delivered:
        if s.actual_delivery and s.created_at:
            region = s.destination_address.split(' ')[0]
            hours  = (s.actual_delivery - s.created_at).total_seconds() / 3600
            region_times[region].append(hours)
    region_avg = {r: round(sum(v) / len(v), 1) for r, v in region_times.items() if v}
    region_sorted = sorted(region_avg.items(), key=lambda x: x[1])[:10]

    # Driver performance ranking
    driver_ranking = sorted(all_d, key=lambda d: d.performance_score(), reverse=True)

    # Monthly trend (last 6 months)
    monthly_data = defaultdict(lambda: {'total': 0, 'delivered': 0, 'on_time': 0, 'revenue': 0})
    for s in all_s:
        k = s.created_at.strftime('%Y-%m')
        monthly_data[k]['total'] += 1
        if s.status == 'delivered':
            monthly_data[k]['delivered'] += 1
            if s.actual_delivery and s.estimated_delivery and s.actual_delivery <= s.estimated_delivery:
                monthly_data[k]['on_time'] += 1
        monthly_data[k]['revenue'] += s.freight_cost or 0
    months = sorted(monthly_data.keys())[-6:]
    monthly_json = [
        {'month': m, **monthly_data[m],
         'on_time_rate': round(monthly_data[m]['on_time'] / monthly_data[m]['delivered'] * 100, 1)
                         if monthly_data[m]['delivered'] else 0}
        for m in months
    ]

    # Priority distribution
    priority_counts = defaultdict(int)
    for s in all_s:
        priority_counts[s.priority] += 1

    # Average delivery duration
    avg_delivery_h = 0
    if delivered:
        total_h = sum((s.actual_delivery - s.created_at).total_seconds() / 3600
                      for s in delivered if s.actual_delivery and s.created_at)
        avg_delivery_h = round(total_h / len(delivered), 1)

    # Total revenue
    total_revenue = sum(s.freight_cost or 0 for s in all_s if s.status != 'cancelled')

    # Fuel cost analysis
    total_fuel_cost = 0
    for s in delivered:
        if s.dispatch and s.distance_km:
            v = s.dispatch.vehicle
            total_fuel_cost += v.trip_fuel_cost(s.distance_km, FUEL_PRICE_KRW)

    return render_template('performance.html',
                           delivered=delivered,
                           on_time_pct=on_time_pct,
                           sla_data=sla_data,
                           region_sorted=region_sorted,
                           driver_ranking=driver_ranking,
                           monthly_json=json.dumps(monthly_json),
                           priority_counts=json.dumps(dict(priority_counts)),
                           avg_delivery_h=avg_delivery_h,
                           total_revenue=total_revenue,
                           total_fuel_cost=total_fuel_cost,
                           total_delivered=len(delivered),
                           total_shipments=len(all_s))


# ── Reports ───────────────────────────────────────────────────────────────────
@app.route('/reports')
def reports():
    all_s = Shipment.query.all()
    all_v = Vehicle.query.all()

    status_counts   = defaultdict(int)
    priority_counts = defaultdict(int)
    for s in all_s:
        status_counts[s.status]   += 1
        priority_counts[s.priority] += 1

    monthly_cnt  = defaultdict(int)
    monthly_cost = defaultdict(float)
    for s in all_s:
        k = s.created_at.strftime('%b %Y')
        monthly_cnt[k]  += 1
        monthly_cost[k] += s.freight_cost or 0
    months = sorted(monthly_cnt.keys(), key=lambda x: datetime.strptime(x, '%b %Y'))[-6:]

    v_util = {'available': 0, 'on_route': 0, 'maintenance': 0}
    for v in all_v:
        v_util[v.status] = v_util.get(v.status, 0) + 1

    delivered = [s for s in all_s if s.status == 'delivered']
    on_time   = sum(1 for s in delivered
                    if s.actual_delivery and s.estimated_delivery and
                    s.actual_delivery <= s.estimated_delivery)
    on_time_pct = round(on_time / len(delivered) * 100) if delivered else 0

    cust_counts, cust_costs = defaultdict(int), defaultdict(float)
    for s in all_s:
        cust_counts[s.customer_name] += 1
        cust_costs[s.customer_name]  += s.freight_cost or 0
    top_customers = sorted(cust_counts.items(), key=lambda x: x[1], reverse=True)[:8]

    total_revenue = sum(s.freight_cost or 0 for s in all_s if s.status != 'cancelled')
    avg_dist      = (sum(s.distance_km or 0 for s in all_s) / len(all_s)) if all_s else 0

    return render_template('reports.html',
                           all_s=all_s,
                           status_json=json.dumps(dict(status_counts)),
                           priority_json=json.dumps(dict(priority_counts)),
                           monthly_json=json.dumps([
                               {'month': m, 'count': monthly_cnt[m],
                                'cost': round(monthly_cost[m], 2)} for m in months
                           ]),
                           vehicle_util_json=json.dumps(v_util),
                           on_time_pct=on_time_pct,
                           top_customers=top_customers,
                           cust_costs=cust_costs,
                           total_revenue=total_revenue,
                           avg_dist=round(avg_dist, 1),
                           total_delivered=len(delivered))


# ── Template filters ──────────────────────────────────────────────────────────
@app.template_filter('from_json')
def from_json(value):
    return json.loads(value) if value else []

@app.template_filter('status_badge')
def status_badge(status):
    return {'pending': 'secondary', 'dispatched': 'info', 'in_transit': 'primary',
            'delivered': 'success', 'cancelled': 'danger'}.get(status, 'secondary')

@app.template_filter('priority_badge')
def priority_badge(priority):
    return {'standard': 'secondary', 'express': 'warning', 'urgent': 'danger'}.get(priority, 'secondary')

@app.template_filter('priority_label')
def priority_label(priority):
    return {'standard': '일반', 'express': '특급', 'urgent': '긴급'}.get(priority, priority)

@app.template_filter('status_label')
def status_label(status):
    return {'pending': '대기', 'dispatched': '배차됨', 'in_transit': '운송중',
            'delivered': '배달완료', 'cancelled': '취소'}.get(status, status)

@app.template_filter('comma')
def comma_filter(value):
    try:
        return f'{int(value):,}'
    except Exception:
        return value


if __name__ == '__main__':
    with app.app_context():
        db.drop_all()
        db.create_all()
        from sample_data import init_sample_data
        init_sample_data()
    app.run(debug=True, port=5001)
