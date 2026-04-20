# FullFit — 뷰티 이커머스 풀필먼트 플랫폼

Multi-role fulfillment operations platform for cosmetics e-commerce sellers in South Korea.

## Roles

| Role   | Description              | Color accent |
|--------|--------------------------|--------------|
| ADMIN  | FullFit operations manager | Dark slate / red |
| WORKER | Warehouse staff          | Emerald green |
| SELLER | Cosmetics seller         | Violet / purple |

---

## Setup

### 1. Backend

```bash
cd fullfit/backend

# (Optional) create a virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set the JWT secret (copy .env.example → .env and edit)
cp ../../.env.example .env

# Start the dev server
uvicorn main:app --reload
# → API available at http://localhost:8000
# → Swagger UI at http://localhost:8000/docs
```

### 2. Frontend

```bash
cd fullfit/frontend

npm install
npm run dev
# → App available at http://localhost:5173
```

---

## Test Accounts

| Role   | Email                  | Password    | Name   |
|--------|------------------------|-------------|--------|
| ADMIN  | admin@fullfit.com      | admin1234   | 김철수 |
| WORKER | worker@fullfit.com     | worker1234  | 이영희 |
| SELLER | seller@fullfit.com     | seller1234  | 홍길동 |

---

## API Endpoints

| Method | Path            | Auth required | Description                  |
|--------|-----------------|---------------|------------------------------|
| POST   | /auth/login     | No            | Get access + refresh tokens  |
| POST   | /auth/refresh   | No            | Exchange refresh → access    |
| GET    | /auth/me        | Yes           | Get current user profile     |

---

## Architecture Notes

- **Access token** — stored in memory only (`window.__fullfit_access_token`). Never written to localStorage.
- **Refresh token** — stored in `localStorage`. Used to silently renew access tokens on page reload or 401.
- **Role enforcement** — enforced at the API level via `require_role()` dependency factory AND at the frontend routing level via `ProtectedRoute`.
- **Password hashing** — bcrypt via `passlib`.

---

## Project Structure

```
fullfit/
├── backend/
│   ├── main.py               # App entry point, CORS, seeding
│   ├── database.py           # SQLAlchemy engine + session
│   ├── models/user.py        # User table + UserRole enum
│   ├── schemas/auth.py       # Pydantic request/response schemas
│   ├── routers/auth.py       # /auth/* endpoints
│   ├── core/
│   │   ├── security.py       # bcrypt + JWT helpers
│   │   └── dependencies.py   # get_current_user, require_role
│   └── requirements.txt
└── frontend/
    ├── src/
    │   ├── api/axiosInstance.js    # Axios + token interceptors
    │   ├── store/authStore.js      # Zustand auth state
    │   ├── routes/ProtectedRoute.jsx
    │   ├── App.jsx                 # Router setup
    │   └── pages/
    │       ├── LoginPage.jsx
    │       ├── admin/AdminDashboard.jsx
    │       ├── worker/WorkerDashboard.jsx
    │       └── seller/SellerDashboard.jsx
    ├── index.html
    ├── package.json
    └── vite.config.js
```
