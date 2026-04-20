from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.dependencies import get_current_user
from core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from database import get_db
from models.user import User
from schemas.auth import (
    AccessTokenResponse,
    LoginRequest,
    RefreshRequest,
    TokenResponse,
    UserResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)):
    """Validate credentials and return access + refresh token pair."""
    user = db.query(User).filter(User.email == request.email).first()

    if not user or not verify_password(request.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="이메일 또는 비밀번호가 올바르지 않습니다.",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="비활성화된 계정입니다. 관리자에게 문의하세요.",
        )

    token_data = {"sub": str(user.id)}
    return TokenResponse(
        access_token=create_access_token(token_data),
        refresh_token=create_refresh_token(token_data),
        role=user.role,
    )


@router.post("/refresh", response_model=AccessTokenResponse)
def refresh_token(body: RefreshRequest, db: Session = Depends(get_db)):
    """Exchange a valid refresh token for a new access token."""
    payload = decode_token(body.refresh_token)

    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="리프레시 토큰이 유효하지 않거나 만료되었습니다.",
        )

    user = db.query(User).filter(User.id == int(payload["sub"])).first()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="사용자를 찾을 수 없습니다.",
        )

    return AccessTokenResponse(
        access_token=create_access_token({"sub": str(user.id)})
    )


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """Return the profile of the currently authenticated user."""
    return current_user
