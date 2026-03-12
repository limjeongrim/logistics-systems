from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import os, json, math, sqlite3
from collections import defaultdict

app = Flask(__name__)
app.config['SECRET_KEY'] = 'logibridge-2024'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///bridge.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

bridge_db = SQLAlchemy(app)

BASE    = os.path.dirname(os.path.abspath(__file__))
WMS_DB  = os.path.normpath(os.path.join(BASE, '..', 'wms',  'instance', 'wms.db'))
TMS_DB  = os.path.normpath(os.path.join(BASE, '..', 'tms',  'instance', 'tms.db'))

WMS_URL = 'http://localhost:5000'
TMS_URL = 'http://localhost:5001'

WAREHOUSE_ADDR = '서울특별시 송파구 문정동 물류센터'
WAREHOUSE_LAT  = 37.4690
WAREHOUSE_LNG  = 127.0390

CITIES = [
    ('서울',   37.5665, 126.9780),
    ('부산',   35.1796, 129.0756),
    ('대구',   35.8714, 128.6014),
    ('인천',   37.4563, 126.7052),
    ('광주',   35.1595, 126.8526),
    ('대전',   36.3504, 127.3845),
    ('울산',   35.5384, 129.3114),
    ('수원',   37.2636, 127.0286),
    ('창원',   35.2280, 128.6811),
    ('고양',   37.6584, 126.8320),
    ('전주',   35.8242, 127.1479),
    ('청주',   36.6424, 127.4890),
    ('포항',   36.0190, 129.3435),
    ('안산',   37.3219, 126.8309),
    ('평택',   36.9921, 127.1128),
]

FUEL_PRICE = 1650
SPEED_KMH  = 80


# ── Bridge Model ───────────────────────────────────────────────────────────────
class WmsTmsLink(bridge_db.Model):
    __tablename__ = 'wms_tms_links'
    id                  = bridge_db.Column(bridge_db.Integer, primary_key=True)
    wms_transaction_id  = bridge_db.Column(bridge_db.Integer, unique=True, nullable=False)
    wms_reference       = bridge_db.Column(bridge_db.String(100))
    product_name        = bridge_db.Column(bridge_db.String(200))
    quantity            = bridge_db.Column(bridge_db.Integer, default=0)
    weight_kg           = bridge_db.Column(bridge_db.Float, default=0)
    customer_name       = bridge_db.Column(bridge_db.String(100))
    dest_city           = bridge_db.Column(bridge_db.String(50))
    tms_shipment_id     = bridge_db.Column(bridge_db.Integer)
    tms_shipment_number = bridge_db.Column(bridge_db.String(20))
    # pending / tms_registered / dispatched / delivered
    status              = bridge_db.Column(bridge_db.String(20), default='pending')
    created_at          = bridge_db.Column(bridge_db.DateTime, default=datetime.utcnow)
    updated_at          = bridge_db.Column(bridge_db.DateTime, default=datetime.utcnow)


# ── DB helpers ─────────────────────────────────────────────────────────────────
def _query(path, sql, params=None):
    if not os.path.exists(path):
        return []
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql, params or []).fetchall()]
    finally:
        conn.close()


def _scalar(path, sql, params=None):
    rows = _query(path, sql, params)
    return list(rows[0].values())[0] if rows else 0


def _execute(path, sql, params=None):
    conn = sqlite3.connect(path)
    try:
        cur = conn.execute(sql, params or [])
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def wq(sql, p=None):  return _query(WMS_DB, sql, p)
def ws(sql, p=None):  return _scalar(WMS_DB, sql, p)
def tq(sql, p=None):  return _query(TMS_DB, sql, p)
def ts(sql, p=None):  return _scalar(TMS_DB, sql, p)
def tx(sql, p=None):  return _execute(TMS_DB, sql, p)


# ── Geo helper ─────────────────────────────────────────────────────────────────
def haversine(lat1, lng1, lat2, lng2):
    R = 6371
    f1, f2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin(math.radians(lat2 - lat1) / 2) ** 2 +
         math.cos(f1) * math.cos(f2) * math.sin(math.radians(lng2 - lng1) / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ── Sync bridge statuses from TMS ─────────────────────────────────────────────
def _sync_link_statuses():
    """Pull latest TMS shipment statuses into bridge links."""
    links = WmsTmsLink.query.filter(
        WmsTmsLink.tms_shipment_id.isnot(None),
        WmsTmsLink.status.notin_(['delivered', 'cancelled'])
    ).all()
    if not links:
        return
    ids = [l.tms_shipment_id for l in links]
    rows = tq(f"SELECT id, status FROM shipments WHERE id IN ({','.join('?'*len(ids))})", ids)
    status_map = {r['id']: r['status'] for r in rows}
    for link in links:
        tms_status = status_map.get(link.tms_shipment_id)
        if not tms_status:
            continue
        if tms_status == 'delivered':
            link.status = 'delivered'
        elif tms_status in ('dispatched', 'in_transit'):
            link.status = 'dispatched'
        link.updated_at = datetime.utcnow()
    bridge_db.session.commit()


# ── Dashboard ──────────────────────────────────────────────────────────────────
@app.route('/')
def dashboard():
    _sync_link_statuses()
    today = datetime.utcnow().strftime('%Y-%m-%d')

    # ─ WMS KPIs ─
    wms_total_stock     = ws('SELECT COALESCE(SUM(quantity),0) FROM inventory')
    wms_today_outbound  = ws("SELECT COUNT(*) FROM transactions "
                             "WHERE type='outbound' AND date(created_at)=?", [today])
    wms_low_stock       = ws("SELECT COUNT(*) FROM products p "
                             "JOIN inventory i ON p.id=i.product_id "
                             "WHERE i.quantity <= p.reorder_point")
    wms_pending_wo      = ws("SELECT COUNT(*) FROM work_orders "
                             "WHERE status IN ('pending','in_progress')")
    wms_stock_value     = ws("SELECT COALESCE(SUM(i.quantity * p.unit_price),0) "
                             "FROM inventory i JOIN products p ON i.product_id=p.id") or 0

    # ─ TMS KPIs ─
    tms_total           = ts('SELECT COUNT(*) FROM shipments')
    tms_in_transit      = ts("SELECT COUNT(*) FROM shipments WHERE status='in_transit'")
    tms_dispatched      = ts("SELECT COUNT(*) FROM shipments WHERE status='dispatched'")
    tms_delivered_today = ts("SELECT COUNT(*) FROM shipments "
                             "WHERE status='delivered' AND date(actual_delivery)=?", [today])
    tms_avail_vehicles  = ts("SELECT COUNT(*) FROM vehicles WHERE status='available'")
    tms_over_hours      = ts("SELECT COUNT(*) FROM drivers WHERE working_hours_today > 8.0")
    tms_pending         = ts("SELECT COUNT(*) FROM shipments WHERE status='pending'")
    tms_revenue         = ts("SELECT COALESCE(SUM(freight_cost),0) FROM shipments "
                             "WHERE status != 'cancelled'") or 0

    # ─ Bridge KPIs ─
    bridge_pending      = WmsTmsLink.query.filter_by(status='pending').count()
    bridge_registered   = WmsTmsLink.query.filter_by(status='tms_registered').count()
    bridge_total        = WmsTmsLink.query.count()

    # ─ Order flow funnel ─
    funnel = [
        {'label': 'WMS 출고 요청',   'count': wms_today_outbound,               'icon': 'arrow-up-from-bracket', 'color': 'blue'},
        {'label': 'WMS 피킹 완료',   'count': ws("SELECT COUNT(*) FROM work_orders WHERE status='completed'"), 'icon': 'clipboard-check', 'color': 'cyan'},
        {'label': 'TMS 배송 등록',   'count': tms_pending + bridge_registered,   'icon': 'file-circle-check',    'color': 'purple'},
        {'label': '배차 / 운송 중',  'count': tms_dispatched + tms_in_transit,   'icon': 'truck-fast',           'color': 'amber'},
        {'label': '배달 완료',        'count': ts("SELECT COUNT(*) FROM shipments WHERE status='delivered'"), 'icon': 'circle-check', 'color': 'green'},
    ]

    # ─ Recent linked orders ─
    recent_links = WmsTmsLink.query.order_by(WmsTmsLink.created_at.desc()).limit(10).all()
    # Annotate with TMS shipment data
    tms_ids = [l.tms_shipment_id for l in recent_links if l.tms_shipment_id]
    tms_ship_map = {}
    if tms_ids:
        for row in tq(f"SELECT id, shipment_number, status, priority, destination_address, "
                      f"estimated_delivery FROM shipments WHERE id IN ({','.join('?'*len(tms_ids))})", tms_ids):
            tms_ship_map[row['id']] = row

    # ─ Alerts ─
    alerts = []
    # WMS low stock
    for item in wq("SELECT p.name, p.reorder_point, i.quantity FROM products p "
                   "JOIN inventory i ON p.id=i.product_id "
                   "WHERE i.quantity <= p.reorder_point ORDER BY i.quantity LIMIT 5"):
        level = '재고 없음' if item['quantity'] == 0 else '재고 부족'
        alerts.append({
            'type': 'danger' if item['quantity'] == 0 else 'warning',
            'source': 'WMS', 'icon': 'box-open',
            'msg': f"{item['name']}: {level} (현재 {item['quantity']}개 / 재주문점 {item['reorder_point']}개)",
        })
    # TMS over-hours drivers
    for d in tq("SELECT name, working_hours_today FROM drivers WHERE working_hours_today > 8.0"):
        alerts.append({
            'type': 'warning', 'source': 'TMS', 'icon': 'user-clock',
            'msg': f"기사 {d['name']}: 근무시간 초과 ({d['working_hours_today']:.1f}시간)",
        })
    # TMS overdue maintenance
    for m in tq("SELECT v.plate, m.maintenance_type FROM maintenance_records m "
                "JOIN vehicles v ON m.vehicle_id=v.id WHERE m.status='overdue' LIMIT 4"):
        alerts.append({
            'type': 'danger', 'source': 'TMS', 'icon': 'wrench',
            'msg': f"차량 {m['plate']}: {m['maintenance_type']} 정비 기한 초과",
        })
    # Bridge pending
    if bridge_pending:
        alerts.append({
            'type': 'info', 'source': '연동', 'icon': 'link',
            'msg': f"TMS 등록 대기 중인 출고 요청 {bridge_pending}건 — 주문 관리 페이지에서 처리하세요.",
        })

    # ─ Monthly trend chart ─
    monthly2 = []
    for i in range(5, -1, -1):
        d  = datetime.utcnow() - timedelta(days=30 * i)
        ym = d.strftime('%Y-%m')
        wms_cnt = ws("SELECT COUNT(*) FROM transactions WHERE type='outbound' "
                     "AND strftime('%Y-%m', created_at)=?", [ym])
        tms_cnt = ts("SELECT COUNT(*) FROM shipments WHERE strftime('%Y-%m', created_at)=?", [ym])
        monthly2.append({'month': d.strftime('%m월'), 'wms': wms_cnt, 'tms': tms_cnt})

    return render_template('dashboard.html',
        wms_total_stock=wms_total_stock,
        wms_today_outbound=wms_today_outbound,
        wms_low_stock=wms_low_stock,
        wms_pending_wo=wms_pending_wo,
        wms_stock_value=wms_stock_value,
        tms_total=tms_total,
        tms_in_transit=tms_in_transit,
        tms_dispatched=tms_dispatched,
        tms_delivered_today=tms_delivered_today,
        tms_avail_vehicles=tms_avail_vehicles,
        tms_over_hours=tms_over_hours,
        tms_revenue=tms_revenue,
        bridge_pending=bridge_pending,
        bridge_registered=bridge_registered,
        bridge_total=bridge_total,
        funnel=funnel,
        recent_links=recent_links,
        tms_ship_map=tms_ship_map,
        alerts=alerts,
        monthly_json=json.dumps(monthly2),
        wms_url=WMS_URL, tms_url=TMS_URL,
    )


# ── Orders ─────────────────────────────────────────────────────────────────────
@app.route('/orders')
def orders():
    _sync_link_statuses()

    # WMS outbound transactions (last 60)
    wms_txns = wq(
        "SELECT t.id, t.quantity, t.reference, t.notes, t.created_at, "
        "p.name as product_name, p.sku, p.unit, p.unit_price, p.category "
        "FROM transactions t JOIN products p ON t.product_id=p.id "
        "WHERE t.type='outbound' ORDER BY t.created_at DESC LIMIT 60")

    links_by_txn = {l.wms_transaction_id: l for l in WmsTmsLink.query.all()}

    tms_ids = [l.tms_shipment_id for l in links_by_txn.values() if l.tms_shipment_id]
    tms_ship_map = {}
    if tms_ids:
        for row in tq(f"SELECT id, shipment_number, status, priority, "
                      f"destination_address, estimated_delivery, actual_delivery "
                      f"FROM shipments WHERE id IN ({','.join('?'*len(tms_ids))})", tms_ids):
            tms_ship_map[row['id']] = row

    rows = []
    for txn in wms_txns:
        link = links_by_txn.get(txn['id'])
        tms  = tms_ship_map.get(link.tms_shipment_id) if link and link.tms_shipment_id else None
        rows.append({'txn': txn, 'link': link, 'tms': tms})

    return render_template('orders.html', rows=rows, cities=CITIES, wms_url=WMS_URL, tms_url=TMS_URL)


@app.route('/orders/sync', methods=['POST'])
def sync_outbound():
    """Pull recent WMS outbound transactions into bridge as pending links."""
    txns = wq(
        "SELECT t.id, t.quantity, t.reference, t.created_at, "
        "p.name as product_name, p.unit_price "
        "FROM transactions t JOIN products p ON t.product_id=p.id "
        "WHERE t.type='outbound' ORDER BY t.created_at DESC LIMIT 50")
    added = 0
    for txn in txns:
        if not WmsTmsLink.query.filter_by(wms_transaction_id=txn['id']).first():
            weight_kg = round(max(1.0, (txn['unit_price'] or 10000) / 10000 * 5), 1)
            bridge_db.session.add(WmsTmsLink(
                wms_transaction_id=txn['id'],
                wms_reference=txn['reference'],
                product_name=txn['product_name'],
                quantity=txn['quantity'],
                weight_kg=weight_kg,
                status='pending',
            ))
            added += 1
    bridge_db.session.commit()
    flash(f'WMS 출고 내역 동기화 완료: {added}건 신규 등록됨', 'success')
    return redirect(url_for('orders'))


@app.route('/orders/register', methods=['POST'])
def register_to_tms():
    txn_id        = request.form.get('wms_transaction_id', type=int)
    customer_name = request.form.get('customer_name', '').strip()
    dest_city     = request.form.get('dest_city', '서울')
    priority      = request.form.get('priority', 'standard')
    weight_kg     = request.form.get('weight_kg', type=float) or 50.0
    volume_m3     = request.form.get('volume_m3', type=float) or 0.5

    if not txn_id:
        flash('출고 트랜잭션 ID가 필요합니다.', 'danger')
        return redirect(url_for('orders'))

    txns = wq("SELECT t.*, p.name as product_name, p.unit_price "
              "FROM transactions t JOIN products p ON t.product_id=p.id WHERE t.id=?", [txn_id])
    if not txns:
        flash('WMS 출고 내역을 찾을 수 없습니다.', 'danger')
        return redirect(url_for('orders'))
    txn = txns[0]

    existing = WmsTmsLink.query.filter_by(wms_transaction_id=txn_id).first()
    if existing and existing.tms_shipment_id:
        flash(f'이미 TMS 화물 {existing.tms_shipment_number}에 등록되어 있습니다.', 'warning')
        return redirect(url_for('orders'))

    city_data  = next((c for c in CITIES if c[0] == dest_city), CITIES[0])
    dest_lat, dest_lng = city_data[1], city_data[2]
    dest_addr  = f'{dest_city}시 배송센터'

    dist        = haversine(WAREHOUSE_LAT, WAREHOUSE_LNG, dest_lat, dest_lng)
    rate        = {'standard': 2.5, 'express': 3.2, 'urgent': 4.0}.get(priority, 2.5)
    freight_cost = round(dist * rate + max(0, weight_kg - 100) * 0.02 + max(0, volume_m3 - 1.0) * 15, 2)
    sla_h       = {'urgent': 24, 'express': 36, 'standard': 72}.get(priority, 72)
    est_del     = datetime.utcnow() + timedelta(hours=sla_h)

    count       = ts('SELECT COUNT(*) FROM shipments') + 1
    ship_num    = f'SHP-{datetime.utcnow().strftime("%Y")}-{count:03d}'
    notes_text  = (f'WMS 연동 자동 등록 | '
                   f'출고번호: {txn["reference"] or f"TXN-{txn_id}"} | '
                   f'품목: {txn["product_name"]} × {txn["quantity"]}개')
    now_s  = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    est_s  = est_del.strftime('%Y-%m-%d %H:%M:%S')

    new_id = tx(
        "INSERT INTO shipments (shipment_number, customer_name, "
        "origin_address, origin_lat, origin_lng, "
        "destination_address, destination_lat, destination_lng, "
        "weight_kg, volume_m3, priority, status, freight_cost, distance_km, "
        "notes, created_at, estimated_delivery) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,'pending',?,?,?,?,?)",
        [ship_num, customer_name or txn['reference'] or '미지정 고객',
         WAREHOUSE_ADDR, WAREHOUSE_LAT, WAREHOUSE_LNG,
         dest_addr, dest_lat, dest_lng,
         weight_kg, volume_m3, priority,
         freight_cost, round(dist, 1), notes_text, now_s, est_s])

    tx("INSERT INTO tracking_events (shipment_id, event_type, description, "
       "location_address, location_lat, location_lng, created_at) "
       "VALUES (?,?,?,?,?,?,?)",
       [new_id,
        'created',
        f'WMS 연동 자동 접수 — {txn["product_name"]} × {txn["quantity"]}개',
        WAREHOUSE_ADDR, WAREHOUSE_LAT, WAREHOUSE_LNG, now_s])

    link = existing or WmsTmsLink(wms_transaction_id=txn_id)
    link.wms_reference       = txn['reference']
    link.product_name        = txn['product_name']
    link.quantity            = txn['quantity']
    link.weight_kg           = weight_kg
    link.customer_name       = customer_name or txn['reference'] or '미지정'
    link.dest_city           = dest_city
    link.tms_shipment_id     = new_id
    link.tms_shipment_number = ship_num
    link.status              = 'tms_registered'
    link.updated_at          = datetime.utcnow()
    if not existing:
        bridge_db.session.add(link)
    bridge_db.session.commit()

    flash(f'TMS 화물 {ship_num} 자동 등록 완료! (목적지: {dest_city}, '
          f'거리: {dist:.0f}km, 운임: ₩{freight_cost:,.0f})', 'success')
    return redirect(url_for('orders'))


# ── API ────────────────────────────────────────────────────────────────────────
@app.route('/api/summary')
def api_summary():
    today = datetime.utcnow().strftime('%Y-%m-%d')
    return jsonify({
        'wms': {
            'today_outbound': ws("SELECT COUNT(*) FROM transactions "
                                 "WHERE type='outbound' AND date(created_at)=?", [today]),
            'low_stock': ws("SELECT COUNT(*) FROM products p "
                            "JOIN inventory i ON p.id=i.product_id "
                            "WHERE i.quantity <= p.reorder_point"),
        },
        'tms': {
            'in_transit':      ts("SELECT COUNT(*) FROM shipments WHERE status='in_transit'"),
            'delivered_today': ts("SELECT COUNT(*) FROM shipments "
                                  "WHERE status='delivered' AND date(actual_delivery)=?", [today]),
        },
        'bridge': {
            'pending':    WmsTmsLink.query.filter_by(status='pending').count(),
            'registered': WmsTmsLink.query.filter_by(status='tms_registered').count(),
            'total':      WmsTmsLink.query.count(),
        },
    })


# ── Filters ────────────────────────────────────────────────────────────────────
@app.template_filter('comma')
def comma_filter(v):
    try:    return f'{int(v):,}'
    except: return v


@app.template_filter('short_dt')
def short_dt(v):
    if not v: return '-'
    if isinstance(v, str):
        try: v = datetime.strptime(v[:19], '%Y-%m-%d %H:%M:%S')
        except: return v[:16]
    return v.strftime('%m/%d %H:%M')


@app.template_filter('link_status_label')
def link_status_label(s):
    return {'pending': 'TMS 미등록', 'tms_registered': 'TMS 대기',
            'dispatched': '배송중', 'delivered': '배달완료'}.get(s, s)


@app.template_filter('link_status_color')
def link_status_color(s):
    return {'pending': 'secondary', 'tms_registered': 'info',
            'dispatched': 'primary', 'delivered': 'success'}.get(s, 'secondary')


@app.template_filter('tms_status_label')
def tms_status_label(s):
    return {'pending': '대기', 'dispatched': '배차됨', 'in_transit': '운송중',
            'delivered': '배달완료', 'cancelled': '취소'}.get(s, s or '-')


@app.template_filter('tms_status_color')
def tms_status_color(s):
    return {'pending': 'secondary', 'dispatched': 'info', 'in_transit': 'primary',
            'delivered': 'success', 'cancelled': 'danger'}.get(s, 'secondary')


@app.template_filter('priority_label')
def priority_label(s):
    return {'standard': '일반', 'express': '특급', 'urgent': '긴급'}.get(s, s or '-')


@app.template_filter('priority_color')
def priority_color(s):
    return {'standard': 'secondary', 'express': 'warning', 'urgent': 'danger'}.get(s, 'secondary')


if __name__ == '__main__':
    with app.app_context():
        bridge_db.create_all()
    app.run(debug=True, port=5002)
