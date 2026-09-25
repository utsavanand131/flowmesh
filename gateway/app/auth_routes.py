from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from auth import create_access_token, decode_access_token, hash_password, verify_password
from auth_models import User
from database import SessionLocal


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    name: str | None = Field(default=None, max_length=100)


class LoginRequest(BaseModel):
    email: str
    password: str


def normalize_email(email: str) -> str:
    return email.strip().lower()


def set_auth_cookie(
    response: Response,
    token: str,
) -> None:
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=60 * 60 * 24 * 7,
        path="/",
    )


@router.post("/register")
def register(
    request: RegisterRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    email = normalize_email(request.email)

    existing_user = (
        db.query(User)
        .filter(User.email == email)
        .first()
    )

    if existing_user is not None:
        raise HTTPException(
            status_code=409,
            detail="An account with this email already exists",
        )

    user = User(
        email=email,
        name=request.name,
        password_hash=hash_password(request.password),
    )

    try:
        db.add(user)
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=409,
            detail="An account with this email already exists",
        )

    token = create_access_token(user.id)

    set_auth_cookie(
        response,
        token,
    )

    return {
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
        }
    }


@router.post("/login")
def login(
    request: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    email = normalize_email(request.email)

    user = (
        db.query(User)
        .filter(User.email == email)
        .first()
    )

    if user is None or user.password_hash is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password",
        )

    if not verify_password(
        request.password,
        user.password_hash,
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password",
        )

    token = create_access_token(user.id)

    set_auth_cookie(
        response,
        token,
    )

    return {
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
        }
    }


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(
        key="access_token",
        path="/",
    )

    return {
        "message": "Logged out successfully",
    }


@router.get("/me")
def get_current_user(
    access_token: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
):
    if not access_token:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
        )

    try:
        payload = decode_access_token(access_token)
    except Exception:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired authentication token",
        )

    user_id = payload.get("sub")

    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication token",
        )

    user = db.get(User, user_id)

    if user is None:
        raise HTTPException(
            status_code=401,
            detail="User not found",
        )

    return {
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
        }
    }