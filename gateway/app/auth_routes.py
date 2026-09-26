import os
import secrets
from urllib.parse import urlencode

import httpx

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from auth import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from auth_models import OAuthAccount, User
from database import SessionLocal


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI")

GOOGLE_AUTHORIZATION_URL = (
    "https://accounts.google.com/o/oauth2/v2/auth"
)

GOOGLE_TOKEN_URL = (
    "https://oauth2.googleapis.com/token"
)

GOOGLE_USERINFO_URL = (
    "https://openidconnect.googleapis.com/v1/userinfo"
)

FRONTEND_URL = os.getenv(
    "FRONTEND_URL",
    "http://localhost:3000",
)


def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


class RegisterRequest(BaseModel):
    email: str = Field(
        min_length=3,
        max_length=255,
    )

    password: str = Field(
        min_length=8,
        max_length=128,
    )

    name: str | None = Field(
        default=None,
        max_length=100,
    )


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


def set_oauth_state_cookie(
    response: Response,
    state: str,
) -> None:
    response.set_cookie(
        key="google_oauth_state",
        value=state,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=600,
        path="/auth/google",
    )


def clear_oauth_state_cookie(
    response: Response,
) -> None:
    response.delete_cookie(
        key="google_oauth_state",
        path="/auth/google",
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
        payload = decode_access_token(
            access_token
        )

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

    user = db.get(
        User,
        user_id,
    )

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


@router.get("/google/login")
def google_login():
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=500,
            detail="GOOGLE_CLIENT_ID is not configured",
        )

    if not GOOGLE_REDIRECT_URI:
        raise HTTPException(
            status_code=500,
            detail="GOOGLE_REDIRECT_URI is not configured",
        )

    state = secrets.token_urlsafe(32)

    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "prompt": "select_account",
    }

    authorization_url = (
        f"{GOOGLE_AUTHORIZATION_URL}?"
        f"{urlencode(params)}"
    )

    response = RedirectResponse(
        url=authorization_url,
        status_code=302,
    )

    set_oauth_state_cookie(
        response,
        state,
    )

    return response


@router.get("/google/callback")
def google_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    google_oauth_state: str | None = Cookie(
        default=None,
    ),
    db: Session = Depends(get_db),
):
    if error:
        response = RedirectResponse(
            url=f"{FRONTEND_URL}/login?error=google_auth_denied",
            status_code=302,
        )

        clear_oauth_state_cookie(response)

        return response

    if not code:
        raise HTTPException(
            status_code=400,
            detail="Google authorization code is missing",
        )

    if not state:
        raise HTTPException(
            status_code=400,
            detail="Google OAuth state is missing",
        )

    if not google_oauth_state:
        raise HTTPException(
            status_code=400,
            detail="Google OAuth state cookie is missing",
        )

    if not secrets.compare_digest(
        state,
        google_oauth_state,
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid Google OAuth state",
        )

    if not GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=500,
            detail="GOOGLE_CLIENT_ID is not configured",
        )

    if not GOOGLE_CLIENT_SECRET:
        raise HTTPException(
            status_code=500,
            detail="GOOGLE_CLIENT_SECRET is not configured",
        )

    if not GOOGLE_REDIRECT_URI:
        raise HTTPException(
            status_code=500,
            detail="GOOGLE_REDIRECT_URI is not configured",
        )

    token_data = {
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code",
    }

    try:
        with httpx.Client(
            timeout=10.0
        ) as client:

            token_response = client.post(
                GOOGLE_TOKEN_URL,
                data=token_data,
            )

            token_response.raise_for_status()

            tokens = token_response.json()

            access_token = tokens.get(
                "access_token"
            )

            if not access_token:
                raise HTTPException(
                    status_code=400,
                    detail="Google did not return an access token",
                )

            userinfo_response = client.get(
                GOOGLE_USERINFO_URL,
                headers={
                    "Authorization": (
                        f"Bearer {access_token}"
                    )
                },
            )

            userinfo_response.raise_for_status()

            google_user = userinfo_response.json()

    except httpx.HTTPError:
        raise HTTPException(
            status_code=502,
            detail="Failed to communicate with Google",
        )

    google_account_id = google_user.get("sub")
    google_email = google_user.get("email")
    google_name = google_user.get("name")
    email_verified = google_user.get(
        "email_verified"
    )

    if not google_account_id:
        raise HTTPException(
            status_code=400,
            detail="Google account ID is missing",
        )

    if not google_email:
        raise HTTPException(
            status_code=400,
            detail="Google email is missing",
        )

    if email_verified is not True:
        raise HTTPException(
            status_code=400,
            detail="Google email is not verified",
        )

    email = normalize_email(
        google_email
    )

    oauth_account = (
        db.query(OAuthAccount)
        .filter(
            OAuthAccount.provider == "google",
            OAuthAccount.provider_account_id
            == google_account_id,
        )
        .first()
    )

    if oauth_account is not None:
        user = db.get(
            User,
            oauth_account.user_id,
        )

        if user is None:
            raise HTTPException(
                status_code=500,
                detail="OAuth account is linked to a missing user",
            )

    else:
        user = (
            db.query(User)
            .filter(User.email == email)
            .first()
        )

        if user is None:
            user = User(
                email=email,
                name=google_name,
                password_hash=None,
            )

            db.add(user)
            db.flush()

        oauth_account = OAuthAccount(
            user_id=user.id,
            provider="google",
            provider_account_id=google_account_id,
        )

        db.add(oauth_account)

        try:
            db.commit()

        except IntegrityError:
            db.rollback()

            existing_account = (
                db.query(OAuthAccount)
                .filter(
                    OAuthAccount.provider
                    == "google",
                    OAuthAccount.provider_account_id
                    == google_account_id,
                )
                .first()
            )

            if existing_account is None:
                raise HTTPException(
                    status_code=409,
                    detail="Unable to link Google account",
                )

            user = db.get(
                User,
                existing_account.user_id,
            )

            if user is None:
                raise HTTPException(
                    status_code=500,
                    detail="OAuth account is linked to a missing user",
                )

    token = create_access_token(
        user.id
    )

    response = RedirectResponse(
        url=FRONTEND_URL,
        status_code=302,
    )

    set_auth_cookie(
        response,
        token,
    )

    clear_oauth_state_cookie(
        response,
    )

    return response