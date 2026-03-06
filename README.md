# Logistics Systems — WMS + TMS

A suite of two independent web applications for logistics and supply chain management research, built with Python Flask.

| System | Description | Port |
|---|---|---|
| **WMS** | Warehouse Management System | `5000` |
| **TMS** | Transportation Management System | `5001` |

---

## Quick Start

```bash
git clone https://github.com/limjeongrim/logistics-systems.git
cd logistics-systems

python -m venv venv
# Windows: venv\Scripts\activate
# macOS/Linux: source venv/bin/activate

pip install -r wms/requirements.txt   # same packages for both
```

**Run WMS** (http://localhost:5000):
```bash
cd wms
python app.py
```

**Run TMS** (http://localhost:5001):
```bash
cd tms
python app.py
```

Both apps auto-create their SQLite database and load sample data on first run.

---

## WMS — Warehouse Management System

> See [`wms/`](wms/) for full source code.

### Features
| Feature | Description |
|---|---|
| Dashboard | Real-time KPIs, 30-day transaction trend chart, stock-by-category chart |
| Inbound / Outbound | Log stock receipts and dispatches with reference and supplier |
| Inventory | Full catalog with search, category filter, visual stock-level bars |
| Low Stock Alerts | Three-tier system: Out of Stock / Below Reorder Point / Warning |
| Demand Forecasting | Weighted moving average + linear trend, 4-week projection |
| Work Orders | Pick orders with location-optimized picking route guide |

### Project Structure
```
wms/
├── app.py               # Flask routes + forecast algorithm
├── models.py            # SQLAlchemy models (Product, Inventory, Transaction, WorkOrder, WorkOrderItem)
├── sample_data.py       # 20 products, 90-day history, 6 work orders
├── requirements.txt
├── templates/           # 10 Jinja2 templates (Bootstrap 5)
└── static/css/          # Custom sidebar + KPI card styles
```

---

## TMS — Transportation Management System

> See [`tms/`](tms/) for full source code. Full docs in [`README-TMS.md`](README-TMS.md).

### Features
| Feature | Description |
|---|---|
| Shipment Registration | Interactive Leaflet.js map with click-to-set origin/destination |
| Vehicle Dispatch | Assign fleet vehicles with capacity and availability validation |
| Route Optimization | Nearest-neighbor TSP heuristic for multi-stop delivery routes |
| Freight Estimation | Real-time cost: distance × vehicle rate × priority multiplier |
| Delivery Tracking | Timeline of all events: Created → Dispatched → In Transit → Delivered |
| Reports | 6 charts: status, revenue, on-time rate, fleet utilization, priority, customers |

### Project Structure
```
tms/
├── app.py               # Flask routes + optimization + freight calculator
├── models.py            # SQLAlchemy models (Vehicle, Shipment, Dispatch, TrackingEvent, ...)
├── sample_data.py       # 10 vehicles, 15 Korean-city shipments, multi-stop routes
├── requirements.txt
├── templates/           # 10 Jinja2 templates (Bootstrap 5 + Leaflet.js)
└── static/css/          # Custom sidebar + map + timeline styles
```

---

## Repository Layout

```
logistics-systems/
├── wms/                 # Warehouse Management System (port 5000)
│   ├── app.py
│   ├── models.py
│   ├── sample_data.py
│   ├── requirements.txt
│   ├── templates/
│   └── static/
├── tms/                 # Transportation Management System (port 5001)
│   ├── app.py
│   ├── models.py
│   ├── sample_data.py
│   ├── requirements.txt
│   ├── templates/
│   └── static/
├── README.md            # This file
└── README-TMS.md        # TMS detailed documentation
```

## Tech Stack

- **Backend:** Python 3.11+, Flask 3.1, SQLAlchemy 2.0, SQLite
- **Frontend:** Bootstrap 5.3, Chart.js 4.4, Font Awesome 6.5
- **Maps (TMS):** Leaflet.js 1.9.4 + OpenStreetMap (no API key required)

## License

MIT License — free for academic and educational use.

---

Built for SCMT Graduate Research | Logistics & Supply Chain Management
