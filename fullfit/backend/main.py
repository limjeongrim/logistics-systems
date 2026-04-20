from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.security import hash_password
from database import SessionLocal, engine
from models.user import Base, User, UserRole
from routers import auth

# Create all DB tables on startup
Base.metadata.create_all(bind=engine)


def seed_users():
    """Insert one test user per role if the users table is empty."""
    db = SessionLocal()
    try:
        if db.query(User).count() > 0:
            return  # Already seeded

        users = [
            User(
                email="admin@fullfit.com",
                hashed_password=hash_password("admin1234"),
                role=UserRole.ADMIN,
                full_name="김철수",
            ),
            User(
                email="worker@fullfit.com",
                hashed_password=hash_password("worker1234"),
                role=UserRole.WORKER,
                full_name="이영희",
            ),
            User(
                email="seller@fullfit.com",
                hashed_password=hash_password("seller1234"),
                role=UserRole.SELLER,
                full_name="홍길동",
            ),
        ]
        db.add_all(users)
        db.commit()
        print("✅ Seeded 3 test users (admin / worker / seller)")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    seed_users()
    yield


app = FastAPI(
    title="FullFit API",
    version="1.0.0",
    description="뷰티 이커머스 풀필먼트 플랫폼 백엔드",
    lifespan=lifespan,
)

# Allow the Vite dev server to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)


@app.get("/", tags=["health"])
def root():
    return {"status": "ok", "message": "FullFit API is running"}
