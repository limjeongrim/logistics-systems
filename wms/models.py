from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


class Supplier(db.Model):
    __tablename__ = 'suppliers'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    contact_person = db.Column(db.String(50))
    phone = db.Column(db.String(20))
    email = db.Column(db.String(100))
    address = db.Column(db.Text)
    lead_time_days = db.Column(db.Integer, default=7)
    rating = db.Column(db.Float, default=3.0)  # 1–5
    category = db.Column(db.String(50))
    notes = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    purchase_orders = db.relationship('PurchaseOrder', backref='supplier', lazy='dynamic')
    products = db.relationship('Product', backref='supplier', foreign_keys='Product.supplier_id', lazy='dynamic')

    def total_orders(self):
        return self.purchase_orders.count()

    def pending_orders(self):
        return self.purchase_orders.filter(PurchaseOrder.status.in_(['sent', 'confirmed'])).count()

    def received_orders(self):
        return self.purchase_orders.filter_by(status='received').count()


class Product(db.Model):
    __tablename__ = 'products'
    id = db.Column(db.Integer, primary_key=True)
    sku = db.Column(db.String(20), unique=True, nullable=False)
    barcode = db.Column(db.String(50), unique=True)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50))
    unit = db.Column(db.String(20), default='EA')
    reorder_point = db.Column(db.Integer, default=10)
    location = db.Column(db.String(20))
    description = db.Column(db.Text)
    unit_price = db.Column(db.Integer, default=0)  # KRW
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'))

    inventory = db.relationship('Inventory', backref='product', uselist=False, cascade='all, delete-orphan')
    transactions = db.relationship('Transaction', backref='product', lazy='dynamic')
    work_order_items = db.relationship('WorkOrderItem', backref='product', lazy='dynamic')
    po_items = db.relationship('PurchaseOrderItem', backref='product', lazy='dynamic')

    def current_stock(self):
        return self.inventory.quantity if self.inventory else 0

    def is_low_stock(self):
        return self.current_stock() <= self.reorder_point

    def stock_status(self):
        stock = self.current_stock()
        if stock == 0:
            return 'out'
        if stock <= self.reorder_point:
            return 'low'
        if stock <= self.reorder_point * 2:
            return 'warning'
        return 'ok'


class Inventory(db.Model):
    __tablename__ = 'inventory'
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False, unique=True)
    quantity = db.Column(db.Integer, default=0, nullable=False)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Transaction(db.Model):
    __tablename__ = 'transactions'
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    type = db.Column(db.String(10), nullable=False)  # 'inbound' or 'outbound'
    quantity = db.Column(db.Integer, nullable=False)
    reference = db.Column(db.String(50))
    supplier = db.Column(db.String(100))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class WorkOrder(db.Model):
    __tablename__ = 'work_orders'
    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(20), unique=True, nullable=False)
    customer = db.Column(db.String(100))
    status = db.Column(db.String(20), default='pending')
    priority = db.Column(db.String(10), default='normal')
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    items = db.relationship('WorkOrderItem', backref='work_order', lazy=True, cascade='all, delete-orphan')

    def completion_rate(self):
        if not self.items:
            return 0
        total_required = sum(i.quantity_required for i in self.items)
        total_picked = sum(i.quantity_picked for i in self.items)
        if total_required == 0:
            return 0
        return round((total_picked / total_required) * 100)

    def is_fully_picked(self):
        return all(i.quantity_picked >= i.quantity_required for i in self.items)


class WorkOrderItem(db.Model):
    __tablename__ = 'work_order_items'
    id = db.Column(db.Integer, primary_key=True)
    work_order_id = db.Column(db.Integer, db.ForeignKey('work_orders.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity_required = db.Column(db.Integer, nullable=False)
    quantity_picked = db.Column(db.Integer, default=0)

    def pick_status(self):
        if self.quantity_picked == 0:
            return 'pending'
        if self.quantity_picked >= self.quantity_required:
            return 'complete'
        return 'partial'


class PurchaseOrder(db.Model):
    __tablename__ = 'purchase_orders'
    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(20), unique=True, nullable=False)
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'), nullable=False)
    status = db.Column(db.String(20), default='draft')  # draft, sent, confirmed, received, cancelled
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expected_date = db.Column(db.DateTime)
    received_date = db.Column(db.DateTime)
    auto_generated = db.Column(db.Boolean, default=False)

    items = db.relationship('PurchaseOrderItem', backref='purchase_order', lazy=True, cascade='all, delete-orphan')

    def total_qty(self):
        return sum(i.quantity_ordered for i in self.items)

    def total_value(self):
        return sum(i.quantity_ordered * i.unit_price for i in self.items)


class PurchaseOrderItem(db.Model):
    __tablename__ = 'purchase_order_items'
    id = db.Column(db.Integer, primary_key=True)
    po_id = db.Column(db.Integer, db.ForeignKey('purchase_orders.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity_ordered = db.Column(db.Integer, nullable=False)
    quantity_received = db.Column(db.Integer, default=0)
    unit_price = db.Column(db.Integer, default=0)  # KRW
