from models import db, Product, Inventory, Transaction, WorkOrder, WorkOrderItem
from datetime import datetime, timedelta
import random

PRODUCTS = [
    # SKU, Name, Category, Unit, Reorder Point, Location, Description
    ('ELEC-001', 'Laptop 15"',          'Electronics',     'EA', 5,  'A1-01', '15-inch business laptop, Intel i7'),
    ('ELEC-002', 'Desktop Monitor 27"', 'Electronics',     'EA', 5,  'A1-02', '27-inch 4K IPS monitor'),
    ('ELEC-003', 'USB-C Keyboard',      'Electronics',     'EA', 10, 'A1-03', 'Wireless USB-C mechanical keyboard'),
    ('ELEC-004', 'Wireless Mouse',      'Electronics',     'EA', 10, 'A1-04', 'Ergonomic wireless mouse'),
    ('ELEC-005', 'HDMI Cable 2m',       'Electronics',     'EA', 20, 'A2-01', 'High-speed HDMI 2.1 cable'),
    ('FURN-001', 'Ergonomic Chair',     'Furniture',       'EA', 3,  'B1-01', 'Adjustable lumbar support office chair'),
    ('FURN-002', 'Standing Desk',       'Furniture',       'EA', 2,  'B1-02', 'Height-adjustable standing desk 160x80cm'),
    ('FURN-003', 'Filing Cabinet',      'Furniture',       'EA', 3,  'B1-03', '4-drawer steel filing cabinet'),
    ('OFFC-001', 'A4 Paper (500 sheets)','Office Supplies','PKG', 50, 'C1-01', 'A4 80gsm premium copy paper'),
    ('OFFC-002', 'Ballpoint Pens (Box)','Office Supplies', 'BOX', 15, 'C1-02', 'Box of 50 black ballpoint pens'),
    ('OFFC-003', 'Sticky Notes Pack',   'Office Supplies', 'PKG', 20, 'C1-03', 'Pack of 12 assorted sticky note pads'),
    ('OFFC-004', 'Heavy-Duty Stapler',  'Office Supplies', 'EA', 8,  'C1-04', 'Desktop stapler, 50-sheet capacity'),
    ('PACK-001', 'Bubble Wrap Roll',    'Packaging',       'ROL', 10, 'D1-01', '50m x 50cm bubble wrap roll'),
    ('PACK-002', 'Cardboard Boxes S',   'Packaging',       'EA', 100,'D1-02', 'Small shipping box 20x20x15cm'),
    ('PACK-003', 'Packing Tape',        'Packaging',       'ROL', 25, 'D1-03', '50m transparent packing tape roll'),
    ('PACK-004', 'Foam Padding Sheet',  'Packaging',       'EA', 30, 'D1-04', '100x200cm foam padding sheet 2cm'),
    ('TOOL-001', 'Hand Truck',          'Tools',           'EA', 2,  'E1-01', '2-wheel folding hand truck 200kg'),
    ('TOOL-002', 'Pallet Jack',         'Tools',           'EA', 1,  'E1-02', 'Manual hydraulic pallet jack 2500kg'),
    ('TOOL-003', 'Thermal Label Printer','Tools',          'EA', 2,  'E1-03', 'Thermal label printer 4"x6"'),
    ('TOOL-004', 'Barcode Scanner',     'Tools',           'EA', 3,  'E1-04', '2D wireless barcode scanner'),
]

# (sku, weekly_avg_outbound, trend, current_stock_override)
DEMAND_PATTERNS = {
    'ELEC-001': (3,   0.05,  None),
    'ELEC-002': (5,   0.10,  None),
    'ELEC-003': (8,   0.08,  None),
    'ELEC-004': (10,  0.12,  None),
    'ELEC-005': (15,  0.15,  3),    # low stock
    'FURN-001': (4,   0.06,  None),
    'FURN-002': (2,   0.04,  None),
    'FURN-003': (2,   0.02,  2),    # low stock
    'OFFC-001': (30,  0.20,  None),
    'OFFC-002': (20,  0.10,  None),
    'OFFC-003': (25,  0.08,  12),   # low stock
    'OFFC-004': (6,   0.03,  4),    # low stock
    'PACK-001': (20,  0.18,  None),
    'PACK-002': (60,  0.25,  None),
    'PACK-003': (35,  0.20,  20),   # low stock
    'PACK-004': (25,  0.15,  None),
    'TOOL-001': (1,   0.01,  1),    # low stock
    'TOOL-002': (0,   0.00,  1),    # low stock
    'TOOL-003': (2,   0.03,  None),
    'TOOL-004': (4,   0.05,  None),
}

WORK_ORDERS_DATA = [
    ('WO-2024-001', 'TechCorp Ltd.',       'completed',   'normal', 'Standard order fulfilled.'),
    ('WO-2024-002', 'Global Office Supply','completed',   'high',   'Urgent restocking order.'),
    ('WO-2024-003', 'StartUp Hub',         'in_progress', 'high',   'Office setup - priority customer.'),
    ('WO-2024-004', 'University Library',  'in_progress', 'normal', 'Semester start equipment.'),
    ('WO-2024-005', 'RetailChain Co.',     'pending',     'urgent', 'Weekly restocking run.'),
    ('WO-2024-006', 'Home Office Depot',   'pending',     'low',    'Bulk stationery order.'),
]


def init_sample_data():
    if Product.query.count() > 0:
        return  # Already initialized

    random.seed(42)
    now = datetime.utcnow()

    # Create products
    product_map = {}
    for sku, name, cat, unit, reorder, loc, desc in PRODUCTS:
        p = Product(sku=sku, name=name, category=cat, unit=unit,
                    reorder_point=reorder, location=loc, description=desc)
        db.session.add(p)
        db.session.flush()
        product_map[sku] = p

    db.session.flush()

    # Generate 90 days of transactions
    for sku, product in product_map.items():
        avg_out, trend, stock_override = DEMAND_PATTERNS.get(sku, (5, 0.0, None))

        running_stock = 0
        daily_txns = []

        for day_offset in range(89, -1, -1):
            txn_date = now - timedelta(days=day_offset)
            week_num = (89 - day_offset) // 7
            adjusted_avg = avg_out * (1 + trend * week_num / 12)

            # Inbound: roughly every 2-3 weeks
            if day_offset % random.randint(14, 21) == 0 or running_stock < 0:
                inbound_qty = int(adjusted_avg * random.uniform(8, 14))
                inbound_qty = max(inbound_qty, 20)
                running_stock += inbound_qty
                daily_txns.append(Transaction(
                    product_id=product.id,
                    type='inbound',
                    quantity=inbound_qty,
                    reference=f'PO-{txn_date.strftime("%Y%m%d")}-{random.randint(100,999)}',
                    supplier=random.choice(['SupplierA Corp', 'B&B Wholesale', 'FastLogix Inc.', 'Prime Distributor']),
                    created_at=txn_date
                ))

            # Outbound: daily with some randomness
            if avg_out > 0 and random.random() < 0.65:
                daily_out = max(1, int(adjusted_avg / 5 * random.uniform(0.5, 2.0)))
                daily_out = min(daily_out, running_stock)
                if daily_out > 0:
                    running_stock -= daily_out
                    daily_txns.append(Transaction(
                        product_id=product.id,
                        type='outbound',
                        quantity=daily_out,
                        reference=f'SO-{txn_date.strftime("%Y%m%d")}-{random.randint(100,999)}',
                        created_at=txn_date
                    ))

        for t in daily_txns:
            db.session.add(t)

        # Set final inventory
        final_qty = stock_override if stock_override is not None else max(running_stock, 0)
        inv = Inventory(product_id=product.id, quantity=final_qty)
        db.session.add(inv)

    db.session.flush()

    # Create work orders
    products_list = list(product_map.values())
    wo_dates = [now - timedelta(days=d) for d in [30, 20, 10, 7, 3, 1]]

    for idx, (order_num, customer, status, priority, notes) in enumerate(WORK_ORDERS_DATA):
        wo = WorkOrder(
            order_number=order_num,
            customer=customer,
            status=status,
            priority=priority,
            notes=notes,
            created_at=wo_dates[idx]
        )
        db.session.add(wo)
        db.session.flush()

        # Pick 3-5 random products for this work order
        num_items = random.randint(3, 5)
        selected = random.sample(products_list, num_items)
        for prod in selected:
            req_qty = random.randint(1, 5)
            if status == 'completed':
                picked_qty = req_qty
            elif status == 'in_progress':
                picked_qty = random.randint(0, req_qty)
            else:
                picked_qty = 0
            item = WorkOrderItem(
                work_order_id=wo.id,
                product_id=prod.id,
                quantity_required=req_qty,
                quantity_picked=picked_qty
            )
            db.session.add(item)

    db.session.commit()
