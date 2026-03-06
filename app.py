from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from models import db, Product, Inventory, Transaction, WorkOrder, WorkOrderItem
from datetime import datetime, timedelta
from collections import defaultdict
import json
import math

app = Flask(__name__)
app.config['SECRET_KEY'] = 'wms-dev-secret-2024'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///wms.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)


def compute_forecast(product_id, weeks_ahead=4):
    """Simple demand forecast using weighted moving average + linear trend."""
    cutoff = datetime.utcnow() - timedelta(days=91)
    txns = Transaction.query.filter_by(product_id=product_id, type='outbound') \
        .filter(Transaction.created_at >= cutoff).all()

    weekly = defaultdict(int)
    now = datetime.utcnow()
    for t in txns:
        diff_days = (now - t.created_at).days
        week_idx = min(diff_days // 7, 12)
        weekly[week_idx] += t.quantity

    # week 0 = most recent, week 12 = oldest
    history = [weekly.get(i, 0) for i in range(12, -1, -1)]  # oldest -> newest

    n = len(history)
    if n == 0 or sum(history) == 0:
        return [0] * weeks_ahead, history

    # Weighted moving average (more weight to recent weeks)
    window = min(6, n)
    weights = list(range(1, window + 1))
    recent = history[-window:]
    wma = sum(w * v for w, v in zip(weights, recent)) / sum(weights)

    # Linear regression slope
    x_mean = (n - 1) / 2
    y_mean = sum(history) / n
    numerator = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(history))
    denominator = sum((i - x_mean) ** 2 for i in range(n))
    slope = numerator / denominator if denominator != 0 else 0

    forecasts = []
    for i in range(1, weeks_ahead + 1):
        val = max(0, wma + slope * i)
        forecasts.append(round(val, 1))

    return forecasts, history


# ─────────────────────────────────────────────
# Dashboard
# ─────────────────────────────────────────────
@app.route('/')
def dashboard():
    total_products = Product.query.count()
    total_stock = db.session.query(db.func.sum(Inventory.quantity)).scalar() or 0
    low_stock_count = sum(1 for p in Product.query.all() if p.is_low_stock())
    pending_orders = WorkOrder.query.filter(WorkOrder.status.in_(['pending', 'in_progress'])).count()

    # Recent transactions (last 10)
    recent_txns = Transaction.query.order_by(Transaction.created_at.desc()).limit(10).all()

    # Inventory by category
    categories = {}
    for p in Product.query.all():
        cat = p.category or 'Uncategorized'
        categories[cat] = categories.get(cat, 0) + p.current_stock()

    # Transaction trend last 30 days
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
        trend_data.append({
            'date': day.strftime('%m/%d'),
            'inbound': int(inbound),
            'outbound': int(outbound)
        })

    return render_template('dashboard.html',
                           total_products=total_products,
                           total_stock=total_stock,
                           low_stock_count=low_stock_count,
                           pending_orders=pending_orders,
                           recent_txns=recent_txns,
                           categories_json=json.dumps(categories),
                           trend_json=json.dumps(trend_data))


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
            flash('Please select a product and enter a valid quantity.', 'danger')
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
        flash(f'Inbound recorded: +{quantity} {product.unit} of {product.name}', 'success')
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
            flash('Please select a product and enter a valid quantity.', 'danger')
            return redirect(url_for('outbound'))

        product = Product.query.get_or_404(product_id)
        current_stock = product.current_stock()

        if quantity > current_stock:
            flash(f'Insufficient stock. Available: {current_stock} {product.unit}', 'danger')
            return redirect(url_for('outbound'))

        txn = Transaction(product_id=product_id, type='outbound', quantity=quantity,
                          reference=reference, notes=notes)
        db.session.add(txn)
        product.inventory.quantity -= quantity
        product.inventory.last_updated = datetime.utcnow()
        db.session.commit()
        flash(f'Outbound recorded: -{quantity} {product.unit} of {product.name}', 'success')
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
            (Product.name.ilike(f'%{search}%')) |
            (Product.sku.ilike(f'%{search}%'))
        )
    products = query.order_by(Product.category, Product.name).all()
    categories = [r[0] for r in db.session.query(Product.category).distinct().order_by(Product.category).all()]

    return render_template('inventory.html', products=products, categories=categories,
                           selected_category=category, search=search)


# ─────────────────────────────────────────────
# Low Stock Alerts
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
# Demand Forecasting
# ─────────────────────────────────────────────
@app.route('/forecast')
def forecast():
    selected_id = request.args.get('product_id', type=int)
    products = Product.query.order_by(Product.name).all()

    # Summary table: forecast for all products
    forecasts_summary = []
    for p in products:
        fcast, _ = compute_forecast(p.id, weeks_ahead=4)
        next_week = fcast[0] if fcast else 0
        four_week = sum(fcast) if fcast else 0
        forecasts_summary.append({
            'product': p,
            'next_week': next_week,
            'four_week': four_week,
            'stock': p.current_stock(),
            'reorder': p.reorder_point,
        })

    # Detailed chart for selected product
    chart_data = None
    selected_product = None
    if selected_id:
        selected_product = Product.query.get(selected_id)
        if selected_product:
            fcast, history = compute_forecast(selected_id, weeks_ahead=4)
            # Build week labels
            hist_labels = [f'W-{12 - i}' for i in range(13)]
            hist_labels[-1] = 'This Wk'
            fcast_labels = [f'W+{i + 1}' for i in range(4)]
            chart_data = {
                'hist_labels': hist_labels,
                'hist_values': history,
                'fcast_labels': fcast_labels,
                'fcast_values': fcast,
            }

    return render_template('forecast.html', products=products,
                           forecasts_summary=forecasts_summary,
                           selected_product=selected_product,
                           chart_data=json.dumps(chart_data) if chart_data else None)


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
            flash('Customer name is required.', 'danger')
            return redirect(url_for('new_workorder'))

        # Filter out empty rows
        items = [(int(pid), int(qty)) for pid, qty in zip(product_ids, quantities)
                 if pid and qty and int(qty) > 0]
        if not items:
            flash('Add at least one item to the work order.', 'danger')
            return redirect(url_for('new_workorder'))

        # Generate order number
        count = WorkOrder.query.count() + 1
        order_number = f'WO-{datetime.utcnow().strftime("%Y")}-{count:03d}'

        wo = WorkOrder(order_number=order_number, customer=customer,
                       priority=priority, notes=notes)
        db.session.add(wo)
        db.session.flush()

        for pid, qty in items:
            woi = WorkOrderItem(work_order_id=wo.id, product_id=pid, quantity_required=qty)
            db.session.add(woi)

        db.session.commit()
        flash(f'Work order {order_number} created successfully.', 'success')
        return redirect(url_for('workorder_detail', order_id=wo.id))

    products = Product.query.order_by(Product.name).all()
    return render_template('workorder_new.html', products=products)


@app.route('/workorders/<int:order_id>')
def workorder_detail(order_id):
    wo = WorkOrder.query.get_or_404(order_id)
    # Sort items by warehouse location for optimized picking route
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
            flash(f'Work order status updated to {new_status.replace("_", " ").title()}.', 'success')

    elif action == 'update_pick':
        for item in wo.items:
            picked_key = f'picked_{item.id}'
            picked_val = request.form.get(picked_key, type=int)
            if picked_val is not None:
                item.quantity_picked = max(0, min(picked_val, item.quantity_required))
        wo.updated_at = datetime.utcnow()
        if wo.is_fully_picked() and wo.status == 'in_progress':
            wo.status = 'completed'
            flash('All items picked! Work order marked as completed.', 'success')
        else:
            flash('Pick quantities updated.', 'success')
        db.session.commit()

    return redirect(url_for('workorder_detail', order_id=order_id))


# ─────────────────────────────────────────────
# API helper
# ─────────────────────────────────────────────
@app.route('/api/products')
def api_products():
    products = Product.query.order_by(Product.name).all()
    return jsonify([{
        'id': p.id, 'sku': p.sku, 'name': p.name,
        'stock': p.current_stock(), 'unit': p.unit,
        'location': p.location, 'category': p.category
    } for p in products])


@app.template_filter('status_badge')
def status_badge(status):
    mapping = {
        'pending':     'secondary',
        'in_progress': 'primary',
        'completed':   'success',
        'cancelled':   'danger',
    }
    return mapping.get(status, 'secondary')


@app.template_filter('priority_badge')
def priority_badge(priority):
    mapping = {
        'low':    'info',
        'normal': 'secondary',
        'high':   'warning',
        'urgent': 'danger',
    }
    return mapping.get(priority, 'secondary')


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        from sample_data import init_sample_data
        init_sample_data()
    app.run(debug=True)
