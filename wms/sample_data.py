from models import db, Product, Inventory, Transaction, WorkOrder, WorkOrderItem, Supplier, PurchaseOrder, PurchaseOrderItem
from datetime import datetime, timedelta
import random

PRODUCTS = [
    # SKU, Barcode, Name, Category, Unit, Reorder, Location, Description, UnitPrice (KRW), SupplierKey
    ('ELEC-001', '8801234560001', '노트북 15인치',        '전자제품', 'EA',  5,  'A1-01', '인텔 i7 탑재 15인치 비즈니스 노트북',    1_200_000, 'ELEC_A'),
    ('ELEC-002', '8801234560002', '모니터 27인치 4K',     '전자제품', 'EA',  5,  'A1-02', '27인치 4K IPS 광시야각 모니터',           480_000,   'ELEC_A'),
    ('ELEC-003', '8801234560003', 'USB-C 무선키보드',     '전자제품', 'EA', 10,  'A1-03', 'USB-C 충전 지원 기계식 무선키보드',        89_000,    'ELEC_B'),
    ('ELEC-004', '8801234560004', '무선 마우스',          '전자제품', 'EA', 10,  'A1-04', '인체공학 설계 무선 마우스',                45_000,    'ELEC_B'),
    ('ELEC-005', '8801234560005', 'HDMI 케이블 2m',       '전자제품', 'EA', 20,  'A2-01', 'HDMI 2.1 고속 케이블 2m',                 15_000,    'ELEC_B'),
    ('FURN-001', '8802345670001', '인체공학 의자',        '가구',     'EA',  3,  'B1-01', '허리 지지대 조절 가능 사무용 의자',        350_000,   'FURN'),
    ('FURN-002', '8802345670002', '높이조절 스탠딩 데스크','가구',     'EA',  2,  'B1-02', '160x80cm 전동 높이조절 스탠딩 데스크',    550_000,   'FURN'),
    ('FURN-003', '8802345670003', '서류 캐비닛 4단',      '가구',     'EA',  3,  'B1-03', '4단 스틸 잠금 서류 캐비닛',               180_000,   'FURN'),
    ('OFFC-001', '8803456780001', 'A4 복사용지 500매',    '사무용품', 'PKG', 50, 'C1-01', 'A4 80g 프리미엄 복사용지 500매',           8_500,    'OFFC'),
    ('OFFC-002', '8803456780002', '볼펜 세트 50개입',     '사무용품', 'BOX', 15, 'C1-02', '흑색 볼펜 50개입 박스',                   12_000,    'OFFC'),
    ('OFFC-003', '8803456780003', '포스트잇 12색 세트',   '사무용품', 'PKG', 20, 'C1-03', '12색 혼합 포스트잇 패드 세트',             7_500,    'OFFC'),
    ('OFFC-004', '8803456780004', '대형 스테이플러',      '사무용품', 'EA',  8,  'C1-04', '50매 용량 데스크탑 스테이플러',            35_000,    'OFFC'),
    ('PACK-001', '8804567890001', '버블랩 롤 50m',        '포장재',   'ROL', 10, 'D1-01', '50m x 50cm 에어캡 버블랩 롤',             18_000,    'PACK'),
    ('PACK-002', '8804567890002', '골판지 박스 소형',     '포장재',   'EA', 100, 'D1-02', '소형 택배박스 20x20x15cm',                    800,    'PACK'),
    ('PACK-003', '8804567890003', '박스 테이프 50m',      '포장재',   'ROL', 25, 'D1-03', '50m 투명 포장 테이프 롤',                  5_500,    'PACK'),
    ('PACK-004', '8804567890004', '완충재 폼 시트',       '포장재',   'EA',  30, 'D1-04', '100x200cm 두께 2cm 완충 폼 시트',          9_500,    'PACK'),
    ('TOOL-001', '8805678900001', '핸드트럭 2륜',         '도구',     'EA',  2,  'E1-01', '200kg 지지 접이식 2륜 핸드트럭',          120_000,   'TOOL'),
    ('TOOL-002', '8805678900002', '팔레트 잭 수동',       '도구',     'EA',  1,  'E1-02', '2500kg 수동 유압 팔레트 잭',              450_000,   'TOOL'),
    ('TOOL-003', '8805678900003', '열전사 라벨 프린터',   '도구',     'EA',  2,  'E1-03', '4x6인치 열전사 라벨 프린터',              280_000,   'TOOL'),
    ('TOOL-004', '8805678900004', '2D 무선 바코드 스캐너', '도구',    'EA',  3,  'E1-04', '2D QR/바코드 무선 스캐너',                180_000,   'TOOL'),
]

DEMAND_PATTERNS = {
    'ELEC-001': (3,   0.05,  None),
    'ELEC-002': (5,   0.10,  None),
    'ELEC-003': (8,   0.08,  None),
    'ELEC-004': (10,  0.12,  None),
    'ELEC-005': (15,  0.15,  3),
    'FURN-001': (4,   0.06,  None),
    'FURN-002': (2,   0.04,  None),
    'FURN-003': (2,   0.02,  2),
    'OFFC-001': (30,  0.20,  None),
    'OFFC-002': (20,  0.10,  None),
    'OFFC-003': (25,  0.08,  12),
    'OFFC-004': (6,   0.03,  4),
    'PACK-001': (20,  0.18,  None),
    'PACK-002': (60,  0.25,  None),
    'PACK-003': (35,  0.20,  20),
    'PACK-004': (25,  0.15,  None),
    'TOOL-001': (1,   0.01,  1),
    'TOOL-002': (0,   0.00,  1),
    'TOOL-003': (2,   0.03,  None),
    'TOOL-004': (4,   0.05,  None),
}

SUPPLIERS_DATA = [
    # key, name, contact, phone, email, address, lead_time, rating, category, notes
    ('ELEC_A', '삼성전자 B2B 직판',     '김민준', '02-3457-8901', 'b2b@samsung-direct.co.kr',
     '서울특별시 강남구 삼성로 129 삼성전자빌딩 3F', 3, 4.8, '전자제품', '삼성전자 공식 B2B 파트너사. 당일/익일 배송 가능.'),
    ('ELEC_B', 'LG 비즈니스 솔루션',    '박서연', '02-6966-3000', 'biz@lg-solutions.co.kr',
     '서울특별시 영등포구 여의대로 128 LG트윈타워 6F', 5, 4.5, '전자제품', 'LG전자 공식 기업 공급사. 주변기기 전문.'),
    ('FURN',   '현대오피스 도매',        '이지호', '031-789-2345', 'order@hyundai-office.co.kr',
     '경기도 성남시 분당구 야탑로 59 현대오피스 물류센터', 7, 4.2, '가구', '국내산 고품질 사무가구 전문 도매상.'),
    ('OFFC',   '대한 문구 유통',         '정윤서', '02-2285-6789', 'sales@daehan-stationery.co.kr',
     '서울특별시 중구 을지로 100 대한빌딩 2F', 5, 4.0, '사무용품', '전국 사무용품 유통망 보유. 대량 주문 할인 가능.'),
    ('PACK',   '코리아 패키징',          '최수아', '032-567-8901', 'sales@korea-pack.co.kr',
     '인천광역시 서구 가정로 143 인천물류단지 A동', 4, 4.6, '포장재', '포장재 전문 제조·유통사. 친환경 소재 라인업 보유.'),
    ('TOOL',   '산업기계 전문상사',      '강도윤', '051-456-7890', 'tools@industry-mach.co.kr',
     '부산광역시 사하구 장림로 77 부산산업단지 3구역', 10, 3.8, '도구', '물류·산업용 장비 전문 수입 유통사.'),
]

WORK_ORDERS_DATA = [
    ('WO-2024-001', '테크코프 주식회사',     'completed',   'normal', '정기 발주 완료.'),
    ('WO-2024-002', '글로벌 오피스 서플라이', 'completed',   'high',   '긴급 재고 보충 주문.'),
    ('WO-2024-003', '스타트업 허브',          'in_progress', 'high',   '신규 오피스 셋업 — 우선 고객.'),
    ('WO-2024-004', '한국대학교 도서관',      'in_progress', 'normal', '학기 초 비품 발주.'),
    ('WO-2024-005', '리테일체인 주식회사',    'pending',     'urgent', '주간 정기 재고 보충.'),
    ('WO-2024-006', '홈오피스 디포',          'pending',     'low',    '사무용품 대량 발주.'),
]


def init_sample_data():
    if Product.query.count() > 0:
        return

    random.seed(42)
    now = datetime.utcnow()

    # ── Suppliers ──────────────────────────────────────────
    supplier_map = {}
    for key, name, contact, phone, email, addr, lead, rating, cat, notes in SUPPLIERS_DATA:
        s = Supplier(name=name, contact_person=contact, phone=phone, email=email,
                     address=addr, lead_time_days=lead, rating=rating,
                     category=cat, notes=notes)
        db.session.add(s)
        db.session.flush()
        supplier_map[key] = s

    # ── Products ───────────────────────────────────────────
    product_map = {}
    for sku, barcode, name, cat, unit, reorder, loc, desc, price, sup_key in PRODUCTS:
        supplier = supplier_map.get(sup_key)
        p = Product(sku=sku, barcode=barcode, name=name, category=cat, unit=unit,
                    reorder_point=reorder, location=loc, description=desc,
                    unit_price=price, supplier_id=supplier.id if supplier else None)
        db.session.add(p)
        db.session.flush()
        product_map[sku] = p

    db.session.flush()

    # ── Transactions (90 days) ─────────────────────────────
    korean_suppliers = ['삼성전자 B2B 직판', 'LG 비즈니스 솔루션', '현대오피스 도매',
                        '대한 문구 유통', '코리아 패키징', '산업기계 전문상사']

    for sku, product in product_map.items():
        avg_out, trend, stock_override = DEMAND_PATTERNS.get(sku, (5, 0.0, None))
        running_stock = 0
        daily_txns = []

        for day_offset in range(89, -1, -1):
            txn_date = now - timedelta(days=day_offset)
            week_num = (89 - day_offset) // 7
            adjusted_avg = avg_out * (1 + trend * week_num / 12)

            if day_offset % random.randint(14, 21) == 0 or running_stock < 0:
                inbound_qty = int(adjusted_avg * random.uniform(8, 14))
                inbound_qty = max(inbound_qty, 20)
                running_stock += inbound_qty
                daily_txns.append(Transaction(
                    product_id=product.id, type='inbound', quantity=inbound_qty,
                    reference=f'PO-{txn_date.strftime("%Y%m%d")}-{random.randint(100,999)}',
                    supplier=random.choice(korean_suppliers),
                    created_at=txn_date
                ))

            if avg_out > 0 and random.random() < 0.65:
                daily_out = max(1, int(adjusted_avg / 5 * random.uniform(0.5, 2.0)))
                daily_out = min(daily_out, running_stock)
                if daily_out > 0:
                    running_stock -= daily_out
                    daily_txns.append(Transaction(
                        product_id=product.id, type='outbound', quantity=daily_out,
                        reference=f'SO-{txn_date.strftime("%Y%m%d")}-{random.randint(100,999)}',
                        created_at=txn_date
                    ))

        for t in daily_txns:
            db.session.add(t)

        final_qty = stock_override if stock_override is not None else max(running_stock, 0)
        db.session.add(Inventory(product_id=product.id, quantity=final_qty))

    db.session.flush()

    # ── Work Orders ────────────────────────────────────────
    products_list = list(product_map.values())
    wo_dates = [now - timedelta(days=d) for d in [30, 20, 10, 7, 3, 1]]

    for idx, (order_num, customer, status, priority, notes) in enumerate(WORK_ORDERS_DATA):
        wo = WorkOrder(order_number=order_num, customer=customer, status=status,
                       priority=priority, notes=notes, created_at=wo_dates[idx])
        db.session.add(wo)
        db.session.flush()

        for prod in random.sample(products_list, random.randint(3, 5)):
            req_qty = random.randint(1, 5)
            picked_qty = req_qty if status == 'completed' else \
                         random.randint(0, req_qty) if status == 'in_progress' else 0
            db.session.add(WorkOrderItem(
                work_order_id=wo.id, product_id=prod.id,
                quantity_required=req_qty, quantity_picked=picked_qty
            ))

    # ── Purchase Orders (history) ──────────────────────────
    suppliers_list = list(supplier_map.values())
    po_statuses = ['received', 'received', 'received', 'confirmed', 'sent', 'draft']
    po_dates = [now - timedelta(days=d) for d in [60, 45, 30, 15, 7, 2]]

    for idx, (status, po_date) in enumerate(zip(po_statuses, po_dates)):
        supplier = suppliers_list[idx % len(suppliers_list)]
        lead = supplier.lead_time_days
        expected = po_date + timedelta(days=lead)
        received = (po_date + timedelta(days=lead + random.randint(-1, 3))
                    if status == 'received' else None)

        po = PurchaseOrder(
            order_number=f'PO-{po_date.strftime("%Y")}-{idx+1:03d}',
            supplier_id=supplier.id, status=status,
            created_at=po_date, expected_date=expected, received_date=received,
            auto_generated=(idx % 3 == 0),
            notes=f'{supplier.name} 정기 발주건'
        )
        db.session.add(po)
        db.session.flush()

        # Pick 2-4 products from this supplier's category
        cat_products = [p for p in products_list
                        if p.category == supplier.category] or products_list[:3]
        for prod in random.sample(cat_products, min(len(cat_products), random.randint(2, 4))):
            qty = random.randint(10, 50)
            db.session.add(PurchaseOrderItem(
                po_id=po.id, product_id=prod.id,
                quantity_ordered=qty,
                quantity_received=qty if status == 'received' else 0,
                unit_price=prod.unit_price
            ))

    db.session.commit()
