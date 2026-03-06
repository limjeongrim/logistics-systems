from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from models import db, Vehicle, Shipment, ShipmentStop, Dispatch, TrackingEvent
from datetime import datetime, timedelta
from collections import defaultdict
import json, math

app = Flask(__name__)
app.config['SECRET_KEY'] = 'tms-dev-secret-2024'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///tms.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)


# ── Helpers ──────────────────────────────────────────────────────────────────
def haversine(lat1, lng1, lat2, lng2):
    R = 6371
    f1, f2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin(math.radians(lat2 - lat1) / 2) ** 2 +
         math.cos(f1) * math.cos(f2) * math.sin(math.radians(lng2 - lng1) / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def route_distance(stops):
    """stops: list of {lat, lng} dicts or (lat, lng) tuples"""
    total = 0.0
    for i in range(len(stops) - 1):
        if isinstance(stops[i], dict):
            total += haversine(stops[i]['lat'], stops[i]['lng'],
                               stops[i+1]['lat'], stops[i+1]['lng'])
        else:
            total += haversine(stops[i][0], stops[i][1], stops[i+1][0], stops[i+1][1])
    return round(total, 1)


def nearest_neighbor_optimize(stops):
    """
    Optimize intermediate stop order using nearest-neighbor heuristic.
    stops: list of dicts with lat/lng/address/type. First = origin, Last = destination.
    Returns (optimized_stops, was_changed).
    """
    if len(stops) <= 2:
        return stops, False
    start, end = stops[0], stops[-1]
    middle = stops[1:-1]
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
    original_order = [s.get('address') for s in stops]
    new_order = [s.get('address') for s in new_stops]
    return new_stops, original_order != new_order


def estimate_freight(distance_km, weight_kg, volume_m3, priority, vehicle_type='truck_medium'):
    rate = {'truck_large': 3.0, 'truck_medium': 2.5, 'van': 1.8,
            'motorcycle': 0.8, 'refrigerated': 3.5}.get(vehicle_type, 2.5)
    base     = distance_km * rate
    w_sur    = max(0, weight_kg  - 100) * 0.02
    v_sur    = max(0, volume_m3  - 1.0) * 15.0
    mult     = {'standard': 1.0, 'express': 1.3, 'urgent': 1.6}.get(priority, 1.0)
    return round((base + w_sur + v_sur) * mult, 2)


# ── Dashboard ─────────────────────────────────────────────────────────────────
@app.route('/')
def dashboard():
    all_shipments  = Shipment.query.all()
    total          = len(all_shipments)
    in_transit     = sum(1 for s in all_shipments if s.status == 'in_transit')
    delivered_today = sum(1 for s in all_shipments
                          if s.status == 'delivered' and s.actual_delivery and
                          s.actual_delivery.date() == datetime.utcnow().date())
    pending        = sum(1 for s in all_shipments if s.status == 'pending')
    avail_vehicles = Vehicle.query.filter_by(status='available').count()

    # GeoJSON for map markers
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
                'number': s.shipment_number,
                'customer': s.customer_name,
                'status': s.status,
                'origin': s.origin_address,
                'dest': s.destination_address,
                'color': color,
                'id': s.id,
                'route': [[s.origin_lat, s.origin_lng]] +
                         [[st.lat, st.lng] for st in s.stops] +
                         [[s.destination_lat, s.destination_lng]],
            }
        })

    # Status counts for pie chart
    status_counts = defaultdict(int)
    for s in all_shipments:
        status_counts[s.status] += 1

    # Monthly volume (last 6 months)
    monthly = defaultdict(int)
    for s in all_shipments:
        key = s.created_at.strftime('%b %Y')
        monthly[key] += 1
    months_sorted = sorted(monthly.keys(),
                           key=lambda x: datetime.strptime(x, '%b %Y'))[-6:]
    monthly_data = [{'month': m, 'count': monthly[m]} for m in months_sorted]

    recent = Shipment.query.order_by(Shipment.created_at.desc()).limit(8).all()

    return render_template('dashboard.html',
                           total=total, in_transit=in_transit,
                           delivered_today=delivered_today, pending=pending,
                           avail_vehicles=avail_vehicles,
                           geojson=json.dumps({'type': 'FeatureCollection', 'features': features}),
                           status_counts=json.dumps(dict(status_counts)),
                           monthly_json=json.dumps(monthly_data),
                           recent=recent)


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
            flash('Please fill all required fields and set locations on the map.', 'danger')
            return redirect(url_for('new_shipment'))

        dist = haversine(origin_lat, origin_lng, dest_lat, dest_lng)
        cost = estimate_freight(dist, weight_kg, volume_m3, priority)
        est_days = max(1, round(dist / 300))

        count  = Shipment.query.count() + 1
        num    = f'SHP-{datetime.utcnow().strftime("%Y")}-{count:03d}'
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
            description=f'Shipment {num} created and queued for dispatch.',
            location_address=origin_addr, location_lat=origin_lat, location_lng=origin_lng
        ))
        db.session.commit()
        flash(f'Shipment {num} created. Estimated freight: ${cost:,.2f}', 'success')
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
        flash('Invalid status.', 'danger')
        return redirect(url_for('shipment_detail', sid=sid))

    s.status = new_st
    if new_st == 'delivered':
        s.actual_delivery = datetime.utcnow()
        if s.dispatch and s.dispatch.vehicle:
            s.dispatch.vehicle.status = 'available'

    evt_map = {
        'dispatched':  ('dispatched',       'Vehicle assigned and en route to pickup.'),
        'in_transit':  ('picked_up',         'Cargo picked up, shipment in transit.'),
        'delivered':   ('delivered',         f'Delivered to {s.customer_name}.'),
        'cancelled':   ('cancelled',         'Shipment cancelled.'),
    }
    if new_st in evt_map:
        etype, edesc = evt_map[new_st]
        desc = note or edesc
        db.session.add(TrackingEvent(
            shipment_id=s.id, event_type=etype, description=desc,
            location_address=s.origin_address, location_lat=s.origin_lat, location_lng=s.origin_lng
        ))

    db.session.commit()
    flash(f'Status updated to {new_st.replace("_"," ").title()}.', 'success')
    return redirect(url_for('shipment_detail', sid=sid))


# ── Dispatch ──────────────────────────────────────────────────────────────────
@app.route('/dispatch')
def dispatch():
    pending_shipments   = Shipment.query.filter_by(status='pending').order_by(Shipment.created_at).all()
    available_vehicles  = Vehicle.query.filter_by(status='available').all()
    active_dispatches   = (Dispatch.query
                           .join(Shipment)
                           .filter(Shipment.status.in_(['dispatched', 'in_transit']))
                           .order_by(Dispatch.assigned_at.desc()).all())
    return render_template('dispatch.html',
                           pending_shipments=pending_shipments,
                           available_vehicles=available_vehicles,
                           active_dispatches=active_dispatches)


@app.route('/dispatch/assign', methods=['POST'])
def assign_vehicle():
    sid        = request.form.get('shipment_id', type=int)
    vid        = request.form.get('vehicle_id',  type=int)
    dnotes     = request.form.get('driver_notes', '').strip()

    s = Shipment.query.get_or_404(sid)
    v = Vehicle.query.get_or_404(vid)

    if s.dispatch:
        flash(f'Shipment {s.shipment_number} is already dispatched.', 'warning')
        return redirect(url_for('dispatch'))

    if v.status != 'available':
        flash(f'Vehicle {v.plate} is not available.', 'danger')
        return redirect(url_for('dispatch'))

    # Check capacity
    if s.weight_kg > v.capacity_kg:
        flash(f'Weight {s.weight_kg} kg exceeds vehicle capacity {v.capacity_kg} kg.', 'danger')
        return redirect(url_for('dispatch'))

    d = Dispatch(shipment_id=sid, vehicle_id=vid, driver_notes=dnotes)
    db.session.add(d)
    s.status = 'dispatched'
    v.status = 'on_route'

    # Recalculate cost with actual vehicle type
    s.freight_cost = estimate_freight(s.distance_km or 0, s.weight_kg,
                                      s.volume_m3, s.priority, v.type)

    db.session.add(TrackingEvent(
        shipment_id=sid, event_type='dispatched',
        description=f'Assigned to {v.type_display()} {v.plate} — Driver: {v.driver_name}.',
        location_address=s.origin_address, location_lat=s.origin_lat, location_lng=s.origin_lng
    ))
    db.session.commit()
    flash(f'Vehicle {v.plate} assigned to {s.shipment_number}.', 'success')
    return redirect(url_for('dispatch'))


# ── Vehicles ──────────────────────────────────────────────────────────────────
@app.route('/vehicles')
def vehicles():
    all_v = Vehicle.query.order_by(Vehicle.type, Vehicle.plate).all()
    avail = sum(1 for v in all_v if v.status == 'available')
    on_rt = sum(1 for v in all_v if v.status == 'on_route')
    maint = sum(1 for v in all_v if v.status == 'maintenance')
    return render_template('vehicles.html', vehicles=all_v,
                           avail=avail, on_rt=on_rt, maint=maint)


@app.route('/vehicles/new', methods=['GET', 'POST'])
def new_vehicle():
    if request.method == 'POST':
        plate       = request.form.get('plate', '').strip().upper()
        vtype       = request.form.get('type', '')
        cap_kg      = request.form.get('capacity_kg',  type=float) or 0
        cap_m3      = request.form.get('capacity_m3',  type=float) or 0
        driver_name = request.form.get('driver_name',  '').strip()
        driver_ph   = request.form.get('driver_phone', '').strip()
        notes       = request.form.get('notes', '').strip()

        if not plate or not vtype:
            flash('Plate and vehicle type are required.', 'danger')
            return redirect(url_for('new_vehicle'))
        if Vehicle.query.filter_by(plate=plate).first():
            flash(f'Plate {plate} already exists.', 'danger')
            return redirect(url_for('new_vehicle'))

        v = Vehicle(plate=plate, type=vtype, capacity_kg=cap_kg, capacity_m3=cap_m3,
                    driver_name=driver_name, driver_phone=driver_ph, notes=notes)
        db.session.add(v)
        db.session.commit()
        flash(f'Vehicle {plate} added to fleet.', 'success')
        return redirect(url_for('vehicles'))

    return render_template('vehicle_new.html')


@app.route('/vehicles/<int:vid>/status', methods=['POST'])
def update_vehicle_status(vid):
    v = Vehicle.query.get_or_404(vid)
    new_st = request.form.get('status')
    if new_st in ('available', 'on_route', 'maintenance'):
        v.status = new_st
        db.session.commit()
        flash(f'Vehicle {v.plate} status set to {new_st}.', 'success')
    return redirect(url_for('vehicles'))


# ── Route Optimization ────────────────────────────────────────────────────────
@app.route('/routes')
def routes_view():
    active = (Shipment.query
              .filter(Shipment.status.in_(['dispatched', 'in_transit']))
              .all())
    # Build map data
    routes_geo = []
    for s in active:
        coords = [[s.origin_lat, s.origin_lng]]
        for st in s.stops:
            coords.append([st.lat, st.lng])
        coords.append([s.destination_lat, s.destination_lng])
        color = '#3b82f6' if s.status == 'in_transit' else '#06b6d4'
        routes_geo.append({
            'id': s.id, 'number': s.shipment_number,
            'customer': s.customer_name, 'status': s.status,
            'coords': coords, 'color': color,
            'origin': s.origin_address, 'dest': s.destination_address,
        })

    # Multi-stop shipments available for optimization
    multi_stop = Shipment.query.filter(Shipment.status.in_(['pending', 'dispatched', 'in_transit'])).all()
    multi_stop = [s for s in multi_stop if len(s.stops) >= 1]

    selected_id = request.args.get('optimize', type=int)
    opt_result  = None
    if selected_id:
        s = Shipment.query.get(selected_id)
        if s:
            all_st    = s.all_stops()
            orig_dist = route_distance(all_st)
            opt_st, changed = nearest_neighbor_optimize(all_st)
            opt_dist  = route_distance(opt_st)
            opt_result = {
                'shipment': s,
                'original': all_st,
                'optimized': opt_st,
                'orig_dist': orig_dist,
                'opt_dist':  opt_dist,
                'saved_km':  round(orig_dist - opt_dist, 1),
                'changed':   changed,
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
        return jsonify({'error': 'Need at least 3 stops (origin + waypoint + destination)'}), 400
    opt, changed = nearest_neighbor_optimize(stops)
    orig_dist = route_distance(stops)
    opt_dist  = route_distance(opt)
    return jsonify({'optimized': opt, 'original_distance': orig_dist,
                    'optimized_distance': opt_dist, 'changed': changed,
                    'saved_km': round(orig_dist - opt_dist, 1)})


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
        return jsonify({'error': 'Missing coordinates'}), 400
    dist = haversine(lat1, lng1, lat2, lng2)
    cost = estimate_freight(dist, weight, volume, pri, vtype)
    return jsonify({'distance_km': round(dist, 1), 'freight_cost': cost})


# ── Reports ───────────────────────────────────────────────────────────────────
@app.route('/reports')
def reports():
    all_s = Shipment.query.all()
    all_v = Vehicle.query.all()

    # Status distribution
    status_counts = defaultdict(int)
    for s in all_s:
        status_counts[s.status] += 1

    # Priority distribution
    priority_counts = defaultdict(int)
    for s in all_s:
        priority_counts[s.priority] += 1

    # Monthly shipments + cost (last 6 months)
    monthly_cnt  = defaultdict(int)
    monthly_cost = defaultdict(float)
    for s in all_s:
        k = s.created_at.strftime('%b %Y')
        monthly_cnt[k]  += 1
        monthly_cost[k] += s.freight_cost or 0
    months = sorted(monthly_cnt.keys(),
                    key=lambda x: datetime.strptime(x, '%b %Y'))[-6:]

    # Vehicle utilization
    v_util = {'available': 0, 'on_route': 0, 'maintenance': 0}
    for v in all_v:
        v_util[v.status] = v_util.get(v.status, 0) + 1

    # On-time delivery rate
    delivered = [s for s in all_s if s.status == 'delivered']
    on_time   = sum(1 for s in delivered
                    if s.actual_delivery and s.estimated_delivery and
                    s.actual_delivery <= s.estimated_delivery)
    on_time_pct = round(on_time / len(delivered) * 100) if delivered else 0

    # Top customers
    cust_counts = defaultdict(int)
    cust_costs  = defaultdict(float)
    for s in all_s:
        cust_counts[s.customer_name] += 1
        cust_costs[s.customer_name] += s.freight_cost or 0
    top_customers = sorted(cust_counts.items(), key=lambda x: x[1], reverse=True)[:8]

    # KPIs
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


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        from sample_data import init_sample_data
        init_sample_data()
    app.run(debug=True, port=5001)
