# LogiWMS — Warehouse Management System

A full-featured Warehouse Management System (WMS) built with Python Flask, designed for academic demonstration and small-to-mid-scale logistics operations.

## Features

| Feature | Description |
|---|---|
| **Dashboard** | Real-time KPIs, 30-day transaction trend chart, stock-by-category donut chart |
| **Inbound Recording** | Log goods received with supplier, PO reference, and quantity |
| **Outbound Recording** | Log goods dispatched with stock validation and SO reference |
| **Inventory Management** | Full product catalog with search, category filter, and visual stock levels |
| **Low Stock Alerts** | Three-tier alert system: Out of Stock / Below Reorder Point / Warning |
| **Demand Forecasting** | Weighted moving average + linear trend projection for next 4 weeks |
| **Work Order Management** | Create pick orders, track fulfillment, location-optimized picking guide |

## Tech Stack

- **Backend:** Python 3.11+, Flask 3.0, SQLAlchemy 2.0
- **Database:** SQLite (zero-configuration)
- **Frontend:** Bootstrap 5.3, Chart.js 4.4, Font Awesome 6.5
- **Sample Data:** 20 products, 90 days of transaction history, 6 work orders

## Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/limjeongrim/logistics-systems.git
cd logistics-systems
```

### 2. Create a virtual environment

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Run the application

```bash
python app.py
```

Open your browser and navigate to **http://localhost:5000**

The database is created automatically on first run, and sample data is loaded immediately — no additional setup required.

## Project Structure

```
logistics-systems/
├── app.py               # Flask routes and application factory
├── models.py            # SQLAlchemy database models
├── sample_data.py       # Sample data initialization (90-day history)
├── requirements.txt     # Python dependencies
├── README.md
├── templates/
│   ├── base.html              # Sidebar layout (Bootstrap 5)
│   ├── dashboard.html         # KPI cards + trend/category charts
│   ├── inbound.html           # Inbound form + history
│   ├── outbound.html          # Outbound form + history
│   ├── inventory.html         # Full inventory table with filters
│   ├── alerts.html            # Low stock alert tiers
│   ├── forecast.html          # Demand forecast charts + summary table
│   ├── workorders.html        # Work order list with status tabs
│   ├── workorder_new.html     # New work order creation form
│   └── workorder_detail.html  # Pick sheet with location guide
└── static/
    └── css/
        └── style.css          # Custom CSS (sidebar, KPI cards, etc.)
```

## Database Models

```
Product        — SKU, name, category, unit, reorder_point, warehouse location
Inventory      — Current stock quantity per product
Transaction    — Inbound/outbound events with timestamp, reference, supplier
WorkOrder      — Customer pick orders with priority and status
WorkOrderItem  — Line items linking work orders to products + picked qty
```

## Demand Forecasting Algorithm

1. Fetch all outbound transactions for the past 90 days
2. Aggregate by calendar week (13 data points)
3. Apply a **Weighted Moving Average** over the last 6 weeks (more weight to recent weeks)
4. Compute a **linear regression slope** across all 13 weeks to detect trend direction
5. Project `WMA + slope × week_offset` for weeks +1 through +4

## Warehouse Location Format

Locations follow the pattern `[Aisle][Row]-[Shelf]`, e.g.:
- `A1-01` → Aisle A, Row 1, Shelf 01
- `D2-03` → Aisle D, Row 2, Shelf 03

The Work Order pick sheet **sorts items by location** (A→Z) to minimize walking distance.

## Screenshots

| Page | Description |
|---|---|
| Dashboard | KPI cards, 30-day trend line chart, category donut chart |
| Inventory | Filterable table with visual stock-level progress bars |
| Alerts | Three-tier color-coded low stock alerts |
| Forecast | Historical vs. forecast bar chart with restocking recommendations |
| Work Order | Location-sorted pick sheet with real-time progress tracking |

## License

MIT License — free for academic and educational use.

---

Built for SCMT Graduate Research | Logistics & Supply Chain Management
