# LogiTMS — Transportation Management System

A full-featured Transportation Management System (TMS) built with Python Flask and Leaflet.js, designed for academic demonstration and logistics research.

## Features

| Feature | Description |
|---|---|
| **Shipment Registration** | Create orders with interactive map-based origin/destination selection |
| **Vehicle Dispatch** | Assign fleet vehicles to pending shipments with capacity validation |
| **Route Optimization** | Nearest-neighbor TSP heuristic for multi-stop delivery routes |
| **Freight Estimation** | Real-time cost calculation (distance × vehicle rate × priority multiplier) |
| **Delivery Tracking** | Timeline-based status tracking: Pending → Dispatched → In Transit → Delivered |
| **Reports & Analytics** | Charts for status, revenue, on-time rate, fleet utilization, top customers |
| **Interactive Map** | Leaflet.js with OpenStreetMap — no API key required |

## Tech Stack

- **Backend:** Python 3.11+, Flask 3.1, SQLAlchemy 2.0
- **Database:** SQLite (zero-configuration)
- **Maps:** Leaflet.js 1.9.4 + OpenStreetMap tiles (free, no API key)
- **Frontend:** Bootstrap 5.3, Chart.js 4.4, Font Awesome 6.5
- **Sample Data:** 10 vehicles, 15 shipments (Korean cities), multi-stop routes

## Getting Started

### 1. Navigate to the TMS folder

```bash
cd logistics-systems/tms
```

### 2. Install dependencies (uses same packages as WMS)

```bash
pip install -r requirements.txt
```

### 3. Run the application

```bash
python app.py
```

Open your browser at **http://localhost:5001**

> The TMS runs on port **5001**, separate from the WMS (port 5000), so both can run simultaneously.

## Project Structure

```
tms/
├── app.py               # Flask routes, optimization logic, freight calculator
├── models.py            # SQLAlchemy models
├── sample_data.py       # 10 vehicles + 15 Korean city shipments
├── requirements.txt
├── templates/
│   ├── base.html              # Dark sidebar layout
│   ├── dashboard.html         # KPI cards + live map + charts
│   ├── shipments.html         # Filterable shipment list
│   ├── shipment_new.html      # New order form with interactive map
│   ├── shipment_detail.html   # Route map + tracking timeline
│   ├── dispatch.html          # Vehicle assignment panel
│   ├── vehicles.html          # Fleet management
│   ├── vehicle_new.html       # Add vehicle form
│   ├── routes.html            # Route optimizer + active routes map
│   └── reports.html           # Analytics dashboard
└── static/
    └── css/
        └── style.css          # Custom CSS (cyan TMS theme)
```

## Database Models

```
Vehicle        — plate, type, capacity_kg/m3, driver, status, home_location
Shipment       — origin/dest coordinates, weight, volume, priority, status, freight_cost
ShipmentStop   — intermediate waypoints (lat/lng/address/order)
Dispatch       — links shipment ↔ vehicle with assignment timestamp
TrackingEvent  — timestamped event log for each shipment
```

## Route Optimization Algorithm

The **Nearest Neighbor** heuristic (greedy approximation of TSP):

1. Start from the **origin** (fixed)
2. At each step, visit the **nearest unvisited** intermediate stop
3. End at the **destination** (fixed)
4. Compare total distance before vs. after optimization

This gives a solution within ~20–25% of optimal in O(n²) time, sufficient for real-time TMS use.

## Freight Cost Formula

```
base_cost = distance_km × rate_per_km
  rate: Large Truck $3.00/km | Medium Truck $2.50/km | Van $1.80/km
        Motorcycle $0.80/km  | Refrigerated $3.50/km

weight_surcharge = max(0, weight_kg - 100) × $0.02/kg
volume_surcharge = max(0, volume_m3 - 1.0) × $15.00/m³

priority_multiplier: Standard ×1.0 | Express ×1.3 | Urgent ×1.6

total_cost = (base + weight_surcharge + volume_surcharge) × priority_multiplier
```

## Sample Data

- **10 vehicles** across 5 types: large/medium trucks, vans, motorcycles, refrigerated
- **15 shipments** between Korean cities (Seoul, Busan, Daegu, Incheon, Gwangju, Daejeon, Ulsan, etc.)
- Statuses: 5 delivered, 3 in transit, 2 dispatched, 5 pending
- **2 multi-stop shipments** for route optimization demo

## Running WMS + TMS Together

```bash
# Terminal 1 — WMS on port 5000
cd logistics-systems
python app.py

# Terminal 2 — TMS on port 5001
cd logistics-systems/tms
python app.py
```

## License

MIT License — free for academic and educational use.

---

Built for SCMT Graduate Research | Logistics & Supply Chain Management
