from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from models import db, Product, Inventory, Transaction, WorkOrder, WorkOrderItem, \
                   Supplier, PurchaseOrder, PurchaseOrderItem
from datetime import datetime, timedelta
from collections import defaultdict
import json
import math
import statistics
import os
import sqlite3 as _sqlite3

app = Flask(__name__)
app.config['SECRET_KEY'] = 'wms-dev-secret-2024'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///wms.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

_BRIDGE_DB = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', 'integration', 'instance', 'bridge.db'))


def _notify_bridge(txn_id, product_name, quantity, reference, unit_price=0):
    """Write new outbound transaction to bridge DB for TMS integration (silent fail)."""
    try:
        if not os.path.exists(_BRIDGE_DB):
            return
        weight_kg = round(max(1.0, (unit_price or 10000) / 10000 * 5), 1)
        conn = _sqlite3.connect(_BRIDGE_DB)
        conn.execute(
            "INSERT OR IGNORE INTO wms_tms_links "
            "(wms_transaction_id, wms_reference, product_name, quantity, weight_kg, "
            " status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, 'pending', datetime('now'), datetime('now'))",
            (txn_id, reference, product_name, quantity, weight_kg))
        conn.commit()
        conn.close()
    except Exception:
        pass  # bridge integration is optional


# ─────────────────────────────────────────────
# Forecasting (enhanced)
# ─────────────────────────────────────────────
def compute_forecast(product_id, weeks_ahead=4):
    """Legacy simple forecast — kept for summary table."""
    cutoff = datetime.utcnow() - timedelta(days=91)
    txns = Transaction.query.filter_by(product_id=product_id, type='outbound') \
        .filter(Transaction.created_at >= cutoff).all()

    weekly = defaultdict(int)
    now = datetime.utcnow()
    for t in txns:
        diff_days = (now - t.created_at).days
        week_idx = min(diff_days // 7, 12)
        weekly[week_idx] += t.quantity

    history = [weekly.get(i, 0) for i in range(12, -1, -1)]
    n = len(history)
    if n == 0 or sum(history) == 0:
        return [0] * weeks_ahead, history

    window = min(6, n)
    weights = list(range(1, window + 1))
    recent = history[-window:]
    wma = sum(w * v for w, v in zip(weights, recent)) / sum(weights)

    x_mean = (n - 1) / 2
    y_mean = sum(history) / n
    numerator = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(history))
    denominator = sum((i - x_mean) ** 2 for i in range(n))
    slope = numerator / denominator if denominator != 0 else 0

    forecasts = [max(0, round(wma + slope * i, 1)) for i in range(1, weeks_ahead + 1)]
    return forecasts, history


def compute_forecast_enhanced(product_id, weeks_ahead=4):
    """
    Enhanced forecast:
    - 26 weeks of history
    - Seasonality detection (monthly indices)
    - Anomaly detection (>2σ flagged)
    - Confidence intervals (±1σ, ±2σ)
    - Forecast vs actual accuracy (MAPE)
    """
    cutoff = datetime.utcnow() - timedelta(days=182)
    txns = Transaction.query.filter_by(product_id=product_id, type='outbound') \
        .filter(Transaction.created_at >= cutoff).all()

    now = datetime.utcnow()

    # Weekly aggregation
    weekly = defaultdict(int)
    for t in txns:
        diff_days = (now - t.created_at).days
        week_idx = min(diff_days // 7, 25)
        weekly[week_idx] += t.quantity

    history = [weekly.get(i, 0) for i in range(25, -1, -1)]  # oldest→newest (26 pts)
    n = len(history)
    empty = sum(history) == 0

    # Monthly seasonality from actual transaction dates
    monthly_sums = defaultdict(list)
    for t in txns:
        monthly_sums[t.created_at.month].append(t.quantity)

    monthly_avg = {m: (sum(v) / len(v) if v else 0) for m, v in monthly_sums.items()}
    for m in range(1, 13):
        monthly_avg.setdefault(m, 0)

    overall_avg = sum(monthly_avg.values()) / 12
    seasonality = {m: round(monthly_avg[m] / overall_avg, 3) if overall_avg > 0 else 1.0
                   for m in range(1, 13)}

    # Anomaly detection (>2σ from mean)
    if not empty and n > 2:
        mean = sum(history) / n
        try:
            std = statistics.stdev(history)
        except Exception:
            std = 0
        anomaly_indices = [i for i, v in enumerate(history)
                           if std > 0 and abs(v - mean) > 2 * std]
        clean = [mean if i in anomaly_indices else v for i, v in enumerate(history)]
    else:
        anomaly_indices = []
        clean = history[:]
        mean = sum(history) / n if n else 0
        std = 0

    if empty:
        return {
            'forecasts': [0] * weeks_ahead,
            'upper_1': [0] * weeks_ahead,
            'lower_1': [0] * weeks_ahead,
            'upper_2': [0] * weeks_ahead,
            'lower_2': [0] * weeks_ahead,
            'history': history[-13:],
            'anomaly_indices': [],
            'seasonality': [seasonality.get(m, 1.0) for m in range(1, 13)],
            'accuracy': None,
            'mean': 0, 'std': 0,
        }

    # WMA on clean history
    window = min(6, n)
    weights = list(range(1, window + 1))
    wma = sum(w * v for w, v in zip(weights, clean[-window:])) / sum(weights)

    # Linear regression slope
    x_mean = (n - 1) / 2
    y_mean = sum(clean) / n
    num = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(clean))
    den = sum((i - x_mean) ** 2 for i in range(n))
    slope = num / den if den != 0 else 0

    # Confidence interval width based on historical std dev
    ci_1 = std                         # 1σ
    ci_2 = std * 2                     # 2σ

    # Generate forecasts
    forecasts, upper_1, lower_1, upper_2, lower_2 = [], [], [], [], []
    for i in range(1, weeks_ahead + 1):
        fcast_month = ((now.month - 1 + (i // 4)) % 12) + 1
        s_idx = seasonality.get(fcast_month, 1.0)
        # Blend base forecast with seasonality (70% WMA+slope, 30% seasonal)
        base = max(0, wma + slope * i)
        adjusted = base * (0.7 + 0.3 * s_idx)
        forecasts.append(round(adjusted, 1))
        upper_1.append(round(adjusted + ci_1, 1))
        lower_1.append(round(max(0, adjusted - ci_1), 1))
        upper_2.append(round(adjusted + ci_2, 1))
        lower_2.append(round(max(0, adjusted - ci_2), 1))

    # Forecast accuracy vs actual (MAPE on last 4-week window)
    accuracy = None
    if len(history) >= 8:
        actual_4wk = sum(history[-4:])
        # Reconstruct what the forecast would have been using weeks -8 to -4
        old_hist = history[:-4]
        if sum(old_hist) > 0 and len(old_hist) >= 4:
            ow = min(6, len(old_hist))
            owts = list(range(1, ow + 1))
            o_wma = sum(w * v for w, v in zip(owts, old_hist[-ow:])) / sum(owts)
            on = len(old_hist)
            oxm = (on - 1) / 2
            oym = sum(old_hist) / on
            onum = sum((j - oxm) * (v - oym) for j, v in enumerate(old_hist))
            oden = sum((j - oxm) ** 2 for j in range(on))
            oslope = onum / oden if oden != 0 else 0
            predicted_4wk = sum(max(0, o_wma + oslope * k) for k in range(1, 5))
            if predicted_4wk > 0:
                mape = abs(actual_4wk - predicted_4wk) / predicted_4wk * 100
                accuracy = round(max(0, 100 - mape), 1)

    # Shift anomaly indices to be relative to displayed last-13 history
    display_start = len(history) - 13
    display_anomalies = [i - display_start for i in anomaly_indices if i >= display_start]

    return {
        'forecasts': forecasts,
        'upper_1': upper_1, 'lower_1': lower_1,
        'upper_2': upper_2, 'lower_2': lower_2,
        'history': history[-13:],
        'anomaly_indices': display_anomalies,
        'seasonality': [seasonality.get(m, 1.0) for m in range(1, 13)],
        'accuracy': accuracy,
        'mean': round(mean, 1),
        'std': round(std, 1),
    }


# ─────────────────────────────────────────────
# Dashboard
# ─────────────────────────────────────────────
@app.route('/')
def dashboard():
    total_products = Product.query.count()
    total_stock = db.session.query(db.func.sum(Inventory.quantity)).scalar() or 0
    low_stock_count = sum(1 for p in Product.query.all() if p.is_low_stock())
    pending_orders = WorkOrder.query.filter(WorkOrder.status.in_(['pending', 'in_progress'])).count()
    pending_pos = PurchaseOrder.query.filter(PurchaseOrder.status.in_(['sent', 'confirmed'])).count()

    recent_txns = Transaction.query.order_by(Transaction.created_at.desc()).limit(10).all()

    categories = {}
    for p in Product.query.all():
        cat = p.category or '미분류'
        categories[cat] = categories.get(cat, 0) + p.current_stock()

    trend_data = []
    for i in range(29, -1, -1):
        day = datetime.utcnow() - timedelta(days=i)
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day.replace(hour=23, minute=59, second=59)
        inbound = db.session.query(db.func.sum(Transaction.quantity)).filter(
            Transaction.type == 'inbound',
            Transaction.created_at >= day_start,
            Transaction.created_at <= day_end
        ).scalar() or 0
        outbound = db.session.query(db.func.sum(Transaction.quantity)).filter(
            Transaction.type == 'outbound',
            Transaction.created_at >= day_start,
            Transaction.created_at <= day_end
        ).scalar() or 0
        trend_data.append({'date': day.strftime('%m/%d'), 'inbound': int(inbound), 'outbound': int(outbound)})

    return render_template('dashboard.html',
                           total_products=total_products,
                           total_stock=total_stock,
                           low_stock_count=low_stock_count,
                           pending_orders=pending_orders,
                           pending_pos=pending_pos,
                           recent_txns=recent_txns,
                           categories_json=json.dumps(categories),
                           trend_json=json.dumps(trend_data))


# ─────────────────────────────────────────────
# Warehouse Map
# ─────────────────────────────────────────────
@app.route('/warehouse-map')
def warehouse_map():
    products = Product.query.all()
    location_map = {p.location: p for p in products if p.location}

    ZONES = [
        ('A', '전자제품 구역', 'primary',   ['A1-01', 'A1-02', 'A1-03', 'A1-04', 'A2-01']),
        ('B', '가구 구역',     'success',   ['B1-01', 'B1-02', 'B1-03']),
        ('C', '사무용품 구역', 'info',      ['C1-01', 'C1-02', 'C1-03', 'C1-04']),
        ('D', '포장재 구역',   'warning',   ['D1-01', 'D1-02', 'D1-03', 'D1-04']),
        ('E', '도구 구역',     'danger',    ['E1-01', 'E1-02', 'E1-03', 'E1-04']),
    ]

    grid_data = []
    stats = {'ok': 0, 'warning': 0, 'low': 0, 'out': 0, 'empty': 0}
    for zone_key, zone_name, color, positions in ZONES:
        cells = []
        for pos in positions:
            p = location_map.get(pos)
            status = p.stock_status() if p else 'empty'
            stats[status] += 1
            cells.append({'location': pos, 'product': p, 'status': status,
                           'stock': p.current_stock() if p else 0})
        grid_data.append({'zone': zone_key, 'name': zone_name, 'color': color, 'cells': cells})

    return render_template('warehouse_map.html', grid_data=grid_data,
                           stats=stats, total_locations=sum(stats.values()))


# ─────────────────────────────────────────────
# Barcode Scan
# ─────────────────────────────────────────────
@app.route('/barcode', methods=['GET', 'POST'])
def barcode():
    if request.method == 'POST':
        action = request.form.get('action')
        product_id = request.form.get('product_id', type=int)
        quantity = request.form.get('quantity', type=int)
        reference = request.form.get('reference', '').strip()
        notes = request.form.get('notes', '').strip()

        if not product_id or not quantity or quantity <= 0:
            flash('상품과 수량을 올바르게 입력하세요.', 'danger')
            return redirect(url_for('barcode'))

        product = Product.query.get_or_404(product_id)

        if action == 'inbound':
            txn = Transaction(product_id=product_id, type='inbound', quantity=quantity,
                              reference=reference or f'BC-IN-{datetime.utcnow().strftime("%Y%m%d%H%M%S")}',
                              notes=notes)
            db.session.add(txn)
            if product.inventory:
                product.inventory.quantity += quantity
                product.inventory.last_updated = datetime.utcnow()
            else:
                db.session.add(Inventory(product_id=product_id, quantity=quantity))
            db.session.commit()
            flash(f'입고 완료: {product.name} +{quantity} {product.unit}', 'success')

        elif action == 'outbound':
            current = product.current_stock()
            if quantity > current:
                flash(f'재고 부족. 현재 재고: {current} {product.unit}', 'danger')
                return redirect(url_for('barcode'))
            txn = Transaction(product_id=product_id, type='outbound', quantity=quantity,
                              reference=reference or f'BC-OUT-{datetime.utcnow().strftime("%Y%m%d%H%M%S")}',
                              notes=notes)
            db.session.add(txn)
            product.inventory.quantity -= quantity
            product.inventory.last_updated = datetime.utcnow()
            db.session.commit()
            flash(f'출고 완료: {product.name} -{quantity} {product.unit}', 'success')

        return redirect(url_for('barcode'))

    recent = Transaction.query.order_by(Transaction.created_at.desc()).limit(15).all()
    return render_template('barcode.html', recent=recent)


@app.route('/api/product-by-barcode/<code>')
def api_barcode(code):
    p = Product.query.filter(
        (Product.barcode == code) | (Product.sku == code)
    ).first()
    if not p:
        return jsonify({'error': '상품을 찾을 수 없습니다.'}), 404
    return jsonify({
        'id': p.id, 'sku': p.sku, 'barcode': p.barcode,
        'name': p.name, 'category': p.category,
        'stock': p.current_stock(), 'unit': p.unit,
        'location': p.location, 'reorder_point': p.reorder_point,
        'status': p.stock_status(), 'unit_price': p.unit_price,
        'description': p.description,
    })


# ─────────────────────────────────────────────
# Inbound
# ─────────────────────────────────────────────
@app.route('/inbound', methods=['GET', 'POST'])
def inbound():
    if request.method == 'POST':
        product_id = request.form.get('product_id', type=int)
        quantity = request.form.get('quantity', type=int)
        reference = request.form.get('reference', '').strip()
        supplier = request.form.get('supplier', '').strip()
        notes = request.form.get('notes', '').strip()

        if not product_id or not quantity or quantity <= 0:
            flash('상품과 수량을 올바르게 입력하세요.', 'danger')
            return redirect(url_for('inbound'))

        product = Product.query.get_or_404(product_id)
        txn = Transaction(product_id=product_id, type='inbound', quantity=quantity,
                          reference=reference, supplier=supplier, notes=notes)
        db.session.add(txn)
        if product.inventory:
            product.inventory.quantity += quantity
            product.inventory.last_updated = datetime.utcnow()
        else:
            db.session.add(Inventory(product_id=product_id, quantity=quantity))
        db.session.commit()
        flash(f'입고 등록: +{quantity} {product.unit} / {product.name}', 'success')
        return redirect(url_for('inbound'))

    products = Product.query.order_by(Product.name).all()
    history = Transaction.query.filter_by(type='inbound').order_by(Transaction.created_at.desc()).limit(20).all()
    return render_template('inbound.html', products=products, history=history)


# ─────────────────────────────────────────────
# Outbound
# ─────────────────────────────────────────────
@app.route('/outbound', methods=['GET', 'POST'])
def outbound():
    if request.method == 'POST':
        product_id = request.form.get('product_id', type=int)
        quantity = request.form.get('quantity', type=int)
        reference = request.form.get('reference', '').strip()
        notes = request.form.get('notes', '').strip()

        if not product_id or not quantity or quantity <= 0:
            flash('상품과 수량을 올바르게 입력하세요.', 'danger')
            return redirect(url_for('outbound'))

        product = Product.query.get_or_404(product_id)
        current_stock = product.current_stock()
        if quantity > current_stock:
            flash(f'재고 부족. 현재 재고: {current_stock} {product.unit}', 'danger')
            return redirect(url_for('outbound'))

        txn = Transaction(product_id=product_id, type='outbound', quantity=quantity,
                          reference=reference, notes=notes)
        db.session.add(txn)
        product.inventory.quantity -= quantity
        product.inventory.last_updated = datetime.utcnow()
        db.session.commit()
        _notify_bridge(txn.id, product.name, quantity, reference, product.unit_price or 0)
        flash(f'출고 등록: -{quantity} {product.unit} / {product.name} — TMS 배송 요청 대기열에 자동 추가됨', 'success')
        return redirect(url_for('outbound'))

    products = Product.query.order_by(Product.name).all()
    history = Transaction.query.filter_by(type='outbound').order_by(Transaction.created_at.desc()).limit(20).all()
    return render_template('outbound.html', products=products, history=history)


# ─────────────────────────────────────────────
# Inventory
# ─────────────────────────────────────────────
@app.route('/inventory')
def inventory():
    category = request.args.get('category', '')
    search = request.args.get('q', '')
    query = Product.query
    if category:
        query = query.filter_by(category=category)
    if search:
        query = query.filter(
            (Product.name.ilike(f'%{search}%')) | (Product.sku.ilike(f'%{search}%'))
        )
    products = query.order_by(Product.category, Product.name).all()
    categories = [r[0] for r in db.session.query(Product.category).distinct().order_by(Product.category).all()]
    return render_template('inventory.html', products=products, categories=categories,
                           selected_category=category, search=search)


# ─────────────────────────────────────────────
# Alerts
# ─────────────────────────────────────────────
@app.route('/alerts')
def alerts():
    all_products = Product.query.all()
    out_of_stock = [p for p in all_products if p.current_stock() == 0]
    low_stock = [p for p in all_products if 0 < p.current_stock() <= p.reorder_point]
    warning = [p for p in all_products if p.reorder_point < p.current_stock() <= p.reorder_point * 2]
    return render_template('alerts.html', out_of_stock=out_of_stock,
                           low_stock=low_stock, warning=warning)


# ─────────────────────────────────────────────
# Demand Forecasting (Enhanced)
# ─────────────────────────────────────────────
@app.route('/forecast')
def forecast():
    selected_id = request.args.get('product_id', type=int)
    products = Product.query.order_by(Product.name).all()

    forecasts_summary = []
    for p in products:
        fcast, _ = compute_forecast(p.id, weeks_ahead=4)
        next_week = fcast[0] if fcast else 0
        four_week = sum(fcast) if fcast else 0
        forecasts_summary.append({
            'product': p, 'next_week': next_week,
            'four_week': four_week, 'stock': p.current_stock(),
            'reorder': p.reorder_point,
        })

    chart_data = None
    selected_product = None
    enhanced = None
    if selected_id:
        selected_product = Product.query.get(selected_id)
        if selected_product:
            enhanced = compute_forecast_enhanced(selected_id, weeks_ahead=4)
            hist_labels = [f'W-{12 - i}' for i in range(13)]
            hist_labels[-1] = '이번주'
            fcast_labels = [f'W+{i + 1}' for i in range(4)]
            chart_data = {
                'hist_labels': hist_labels,
                'hist_values': enhanced['history'],
                'fcast_labels': fcast_labels,
                'fcast_values': enhanced['forecasts'],
                'upper_1': enhanced['upper_1'],
                'lower_1': enhanced['lower_1'],
                'upper_2': enhanced['upper_2'],
                'lower_2': enhanced['lower_2'],
                'anomaly_indices': enhanced['anomaly_indices'],
                'seasonality': enhanced['seasonality'],
                'accuracy': enhanced['accuracy'],
                'mean': enhanced['mean'],
                'std': enhanced['std'],
            }

    return render_template('forecast.html', products=products,
                           forecasts_summary=forecasts_summary,
                           selected_product=selected_product,
                           chart_data=json.dumps(chart_data) if chart_data else None,
                           enhanced=enhanced)


# ─────────────────────────────────────────────
# Suppliers
# ─────────────────────────────────────────────
@app.route('/suppliers')
def suppliers():
    all_suppliers = Supplier.query.order_by(Supplier.name).all()
    return render_template('suppliers.html', suppliers=all_suppliers)


@app.route('/suppliers/<int:supplier_id>')
def supplier_detail(supplier_id):
    s = Supplier.query.get_or_404(supplier_id)
    pos = s.purchase_orders.order_by(PurchaseOrder.created_at.desc()).limit(20).all()
    products = s.products.all()
    return render_template('supplier_detail.html', supplier=s, pos=pos, products=products)


@app.route('/suppliers/new', methods=['GET', 'POST'])
def new_supplier():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        if not name:
            flash('업체명을 입력하세요.', 'danger')
            return redirect(url_for('new_supplier'))
        s = Supplier(
            name=name,
            contact_person=request.form.get('contact_person', '').strip(),
            phone=request.form.get('phone', '').strip(),
            email=request.form.get('email', '').strip(),
            address=request.form.get('address', '').strip(),
            lead_time_days=request.form.get('lead_time_days', 7, type=int),
            rating=request.form.get('rating', 3.0, type=float),
            category=request.form.get('category', '').strip(),
            notes=request.form.get('notes', '').strip(),
        )
        db.session.add(s)
        db.session.commit()
        flash(f'공급업체 "{s.name}" 등록 완료.', 'success')
        return redirect(url_for('suppliers'))
    categories = [r[0] for r in db.session.query(Product.category).distinct().all()]
    return render_template('supplier_form.html', supplier=None, categories=categories)


# ─────────────────────────────────────────────
# Purchase Orders
# ─────────────────────────────────────────────
@app.route('/purchase-orders')
def purchase_orders():
    status_filter = request.args.get('status', '')
    query = PurchaseOrder.query
    if status_filter:
        query = query.filter_by(status=status_filter)
    pos = query.order_by(PurchaseOrder.created_at.desc()).all()
    return render_template('purchase_orders.html', pos=pos, status_filter=status_filter)


@app.route('/purchase-orders/new', methods=['GET', 'POST'])
def new_purchase_order():
    if request.method == 'POST':
        supplier_id = request.form.get('supplier_id', type=int)
        notes = request.form.get('notes', '').strip()
        lead_days = request.form.get('lead_days', 7, type=int)
        product_ids = request.form.getlist('product_id[]')
        quantities = request.form.getlist('quantity[]')
        prices = request.form.getlist('unit_price[]')

        if not supplier_id:
            flash('공급업체를 선택하세요.', 'danger')
            return redirect(url_for('new_purchase_order'))

        items = [(int(pid), int(qty), int(p)) for pid, qty, p in zip(product_ids, quantities, prices)
                 if pid and qty and int(qty) > 0]
        if not items:
            flash('상품을 최소 1개 이상 추가하세요.', 'danger')
            return redirect(url_for('new_purchase_order'))

        count = PurchaseOrder.query.count() + 1
        po = PurchaseOrder(
            order_number=f'PO-{datetime.utcnow().strftime("%Y")}-{count:03d}',
            supplier_id=supplier_id, notes=notes,
            expected_date=datetime.utcnow() + timedelta(days=lead_days),
            status='draft'
        )
        db.session.add(po)
        db.session.flush()
        for pid, qty, price in items:
            db.session.add(PurchaseOrderItem(po_id=po.id, product_id=pid,
                                             quantity_ordered=qty, unit_price=price))
        db.session.commit()
        flash(f'발주서 {po.order_number} 생성 완료.', 'success')
        return redirect(url_for('purchase_order_detail', po_id=po.id))

    suppliers_list = Supplier.query.filter_by(is_active=True).order_by(Supplier.name).all()
    products = Product.query.order_by(Product.name).all()
    return render_template('purchase_order_new.html', suppliers=suppliers_list, products=products)


@app.route('/purchase-orders/auto', methods=['POST'])
def auto_purchase_order():
    """Auto-generate a PO for a low-stock product."""
    product_id = request.form.get('product_id', type=int)
    product = Product.query.get_or_404(product_id)

    if not product.supplier_id:
        flash(f'"{product.name}"에 기본 공급업체가 설정되지 않았습니다.', 'danger')
        return redirect(url_for('alerts'))

    supplier = Supplier.query.get(product.supplier_id)
    restock_qty = product.reorder_point * 3  # order 3× reorder point

    count = PurchaseOrder.query.count() + 1
    po = PurchaseOrder(
        order_number=f'PO-{datetime.utcnow().strftime("%Y")}-{count:03d}',
        supplier_id=supplier.id,
        status='draft', auto_generated=True,
        notes=f'자동 발주: [{product.sku}] {product.name} 재고 부족 감지',
        expected_date=datetime.utcnow() + timedelta(days=supplier.lead_time_days)
    )
    db.session.add(po)
    db.session.flush()
    db.session.add(PurchaseOrderItem(
        po_id=po.id, product_id=product.id,
        quantity_ordered=restock_qty, unit_price=product.unit_price
    ))
    db.session.commit()
    flash(f'자동 발주서 {po.order_number} 생성 ({supplier.name} / {product.name} × {restock_qty}개)', 'success')
    return redirect(url_for('purchase_order_detail', po_id=po.id))


@app.route('/purchase-orders/<int:po_id>')
def purchase_order_detail(po_id):
    po = PurchaseOrder.query.get_or_404(po_id)
    return render_template('purchase_order_detail.html', po=po)


@app.route('/purchase-orders/<int:po_id>/update', methods=['POST'])
def update_purchase_order(po_id):
    po = PurchaseOrder.query.get_or_404(po_id)
    action = request.form.get('action')

    if action == 'send':
        po.status = 'sent'
        flash(f'{po.order_number} 발주 전송 완료.', 'success')
    elif action == 'confirm':
        po.status = 'confirmed'
        flash(f'{po.order_number} 공급업체 확인 완료.', 'success')
    elif action == 'receive':
        po.status = 'received'
        po.received_date = datetime.utcnow()
        # Automatically create inbound transactions
        for item in po.items:
            product = Product.query.get(item.product_id)
            if product and item.quantity_ordered > 0:
                item.quantity_received = item.quantity_ordered
                txn = Transaction(
                    product_id=item.product_id, type='inbound',
                    quantity=item.quantity_ordered,
                    reference=po.order_number,
                    supplier=po.supplier.name,
                    notes=f'발주서 입고: {po.order_number}'
                )
                db.session.add(txn)
                if product.inventory:
                    product.inventory.quantity += item.quantity_ordered
                    product.inventory.last_updated = datetime.utcnow()
                else:
                    db.session.add(Inventory(product_id=product.id, quantity=item.quantity_ordered))
        flash(f'{po.order_number} 입고 처리 완료. 재고가 자동 업데이트되었습니다.', 'success')
    elif action == 'cancel':
        po.status = 'cancelled'
        flash(f'{po.order_number} 발주 취소.', 'warning')

    db.session.commit()
    return redirect(url_for('purchase_order_detail', po_id=po_id))


# ─────────────────────────────────────────────
# Work Orders
# ─────────────────────────────────────────────
@app.route('/workorders')
def workorders():
    status_filter = request.args.get('status', '')
    query = WorkOrder.query
    if status_filter:
        query = query.filter_by(status=status_filter)
    orders = query.order_by(WorkOrder.created_at.desc()).all()
    return render_template('workorders.html', orders=orders, status_filter=status_filter)


@app.route('/workorders/new', methods=['GET', 'POST'])
def new_workorder():
    if request.method == 'POST':
        customer = request.form.get('customer', '').strip()
        priority = request.form.get('priority', 'normal')
        notes = request.form.get('notes', '').strip()
        product_ids = request.form.getlist('product_id[]')
        quantities = request.form.getlist('quantity[]')

        if not customer:
            flash('고객명을 입력하세요.', 'danger')
            return redirect(url_for('new_workorder'))

        items = [(int(pid), int(qty)) for pid, qty in zip(product_ids, quantities)
                 if pid and qty and int(qty) > 0]
        if not items:
            flash('상품을 최소 1개 이상 추가하세요.', 'danger')
            return redirect(url_for('new_workorder'))

        count = WorkOrder.query.count() + 1
        order_number = f'WO-{datetime.utcnow().strftime("%Y")}-{count:03d}'
        wo = WorkOrder(order_number=order_number, customer=customer,
                       priority=priority, notes=notes)
        db.session.add(wo)
        db.session.flush()
        for pid, qty in items:
            db.session.add(WorkOrderItem(work_order_id=wo.id, product_id=pid, quantity_required=qty))
        db.session.commit()
        flash(f'작업지시서 {order_number} 생성 완료.', 'success')
        return redirect(url_for('workorder_detail', order_id=wo.id))

    products = Product.query.order_by(Product.name).all()
    return render_template('workorder_new.html', products=products)


@app.route('/workorders/<int:order_id>')
def workorder_detail(order_id):
    wo = WorkOrder.query.get_or_404(order_id)
    sorted_items = sorted(wo.items, key=lambda i: i.product.location or '')
    return render_template('workorder_detail.html', wo=wo, sorted_items=sorted_items)


@app.route('/workorders/<int:order_id>/update', methods=['POST'])
def update_workorder(order_id):
    wo = WorkOrder.query.get_or_404(order_id)
    action = request.form.get('action')

    if action == 'update_status':
        new_status = request.form.get('status')
        if new_status in ('pending', 'in_progress', 'completed', 'cancelled'):
            wo.status = new_status
            wo.updated_at = datetime.utcnow()
            db.session.commit()
            flash(f'작업지시서 상태가 변경되었습니다.', 'success')

    elif action == 'update_pick':
        for item in wo.items:
            picked_val = request.form.get(f'picked_{item.id}', type=int)
            if picked_val is not None:
                item.quantity_picked = max(0, min(picked_val, item.quantity_required))
        wo.updated_at = datetime.utcnow()
        if wo.is_fully_picked() and wo.status == 'in_progress':
            wo.status = 'completed'
            flash('전체 피킹 완료! 작업지시서가 완료 처리되었습니다.', 'success')
        else:
            flash('피킹 수량이 업데이트되었습니다.', 'success')
        db.session.commit()

    return redirect(url_for('workorder_detail', order_id=order_id))


# ─────────────────────────────────────────────
# API helpers
# ─────────────────────────────────────────────
@app.route('/api/products')
def api_products():
    products = Product.query.order_by(Product.name).all()
    return jsonify([{
        'id': p.id, 'sku': p.sku, 'name': p.name,
        'stock': p.current_stock(), 'unit': p.unit,
        'location': p.location, 'category': p.category,
        'unit_price': p.unit_price,
    } for p in products])


# ─────────────────────────────────────────────
# Template filters
# ─────────────────────────────────────────────
@app.template_filter('status_badge')
def status_badge(status):
    return {'pending': 'secondary', 'in_progress': 'primary',
            'completed': 'success', 'cancelled': 'danger'}.get(status, 'secondary')


@app.template_filter('priority_badge')
def priority_badge(priority):
    return {'low': 'info', 'normal': 'secondary',
            'high': 'warning', 'urgent': 'danger'}.get(priority, 'secondary')


@app.template_filter('po_status_badge')
def po_status_badge(status):
    return {'draft': 'secondary', 'sent': 'primary', 'confirmed': 'info',
            'received': 'success', 'cancelled': 'danger'}.get(status, 'secondary')


@app.template_filter('po_status_label')
def po_status_label(status):
    return {'draft': '초안', 'sent': '발송됨', 'confirmed': '확인됨',
            'received': '입고완료', 'cancelled': '취소'}.get(status, status)


@app.template_filter('comma')
def comma_filter(value):
    try:
        return f'{int(value):,}'
    except Exception:
        return value


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        from sample_data import init_sample_data
        init_sample_data()
    app.run(debug=True)
