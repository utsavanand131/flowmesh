import base64
import hashlib
import os
import secrets
from urllib.parse import urlencode
import httpx
from dotenv import load_dotenv
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
load_dotenv()
router = APIRouter(prefix="/auth", tags=["Authentication"])
# -------------------------------------------------------------------
# Environment variables
# -------------------------------------------------------------------
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI")
GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET")
GITHUB_REDIRECT_URI = os.getenv("GITHUB_REDIRECT_URI")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3001")
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
COOKIE_SAMESITE = os.getenv("COOKIE_SAMESITE", "lax").lower()
if COOKIE_SAMESITE not in {"lax", "strict", "none"}:
    raise ValueError("COOKIE_SAMESITE must be 'lax', 'strict', or 'none'")
if COOKIE_SAMESITE == "none" and not COOKIE_SECURE:
    raise ValueError("COOKIE_SECURE must be true when COOKIE_SAMESITE is 'none'")
# -------------------------------------------------------------------
# OAuth endpoints
# -------------------------------------------------------------------
GOOGLE_AUTHORIZATION_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
GITHUB_AUTHORIZATION_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"
GITHUB_EMAILS_URL = "https://api.github.com/user/emails"
# -------------------------------------------------------------------
# Database dependency
# -------------------------------------------------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
# -------------------------------------------------------------------
# Request models
# -------------------------------------------------------------------
class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    name: str | None = Field(default=None, max_length=100)
class LoginRequest(BaseModel):
    email: str
    password: str
# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------
def normalize_email(email: str) -> str:
    return email.strip().lower()
def set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        max_age=60 * 60 * 24 * 7,
        path="/",
    )
def set_google_oauth_state_cookie(response: Response, state: str) -> None:
    response.set_cookie(
        key="google_oauth_state",
        value=state,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        max_age=600,
        path="/auth/google",
    )
def clear_google_oauth_state_cookie(response: Response) -> None:
    response.delete_cookie(
        key="google_oauth_state",
        path="/auth/google",
        secure=COOKIE_SECURE,
        httponly=True,
        samesite=COOKIE_SAMESITE,
    )
def set_github_oauth_state_cookie(response: Response, state: str) -> None:
    response.set_cookie(
        key="github_oauth_state",
        value=state,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        max_age=600,
        path="/auth/github",
    )
def clear_github_oauth_state_cookie(response: Response) -> None:
    response.delete_cookie(
        key="github_oauth_state",
        path="/auth/github",
        secure=COOKIE_SECURE,
        httponly=True,
        samesite=COOKIE_SAMESITE,
    )
def set_github_code_verifier_cookie(
    response: Response,
    code_verifier: str,
) -> None:
    response.set_cookie(
        key="github_code_verifier",
        value=code_verifier,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        max_age=600,
        path="/auth/github",
    )
def clear_github_code_verifier_cookie(response: Response) -> None:
    response.delete_cookie(
        key="github_code_verifier",
        path="/auth/github",
        secure=COOKIE_SECURE,
        httponly=True,
        samesite=COOKIE_SAMESITE,
    )
def create_pkce_code_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(
        code_verifier.encode("utf-8")
    ).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("utf-8")
# -------------------------------------------------------------------
# Email/password registration
# -------------------------------------------------------------------
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
            detail="Email is already registered",
        )
    user = User(
        email=email,
        name=request.name,
        password_hash=hash_password(request.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(user.id)
    set_auth_cookie(response, token)
    return {
        "message": "Registration successful",
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
        },
    }
# -------------------------------------------------------------------
# Email/password login
# -------------------------------------------------------------------
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
    set_auth_cookie(response, token)
    return {
        "message": "Login successful",
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
        },
    }
# -------------------------------------------------------------------
# Logout
# -------------------------------------------------------------------
@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(
        key="access_token",
        path="/",
        secure=COOKIE_SECURE,
        httponly=True,
        samesite=COOKIE_SAMESITE,
    )
    return {
        "message": "Logout successful",
    }
# -------------------------------------------------------------------
# Current authenticated user
# -------------------------------------------------------------------
def require_current_user(
    access_token: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> User:
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
            detail="Invalid or expired token",
        )

    user_id = payload.get("sub")

    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="Invalid token",
        )

    user = db.get(User, user_id)

    if user is None:
        raise HTTPException(
            status_code=401,
            detail="User not found",
        )

    return user


@router.get("/me")
def get_current_user(
    user: User = Depends(require_current_user),
):
    return {
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
        }
    }

# ===================================================================
# GOOGLE OAUTH
# ===================================================================
# -------------------------------------------------------------------
# Google login
# -------------------------------------------------------------------
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
        f"{GOOGLE_AUTHORIZATION_URL}?{urlencode(params)}"
    )
    response = RedirectResponse(
        url=authorization_url,
        status_code=302,
    )
    set_google_oauth_state_cookie(response, state)
    return response
# -------------------------------------------------------------------
# Google callback
# -------------------------------------------------------------------
@router.get("/google/callback")
def google_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    google_oauth_state: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
):
    if error:
        response = RedirectResponse(
            url=f"{FRONTEND_URL}/login?error=google_auth_denied",
            status_code=302,
        )
        clear_google_oauth_state_cookie(response)
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
    if not secrets.compare_digest(state, google_oauth_state):
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
        with httpx.Client(timeout=10.0) as client:
            token_response = client.post(
                GOOGLE_TOKEN_URL,
                data=token_data,
            )
            token_response.raise_for_status()
            tokens = token_response.json()
            access_token = tokens.get("access_token")
            if not access_token:
                raise HTTPException(
                    status_code=400,
                    detail="Google did not return an access token",
                )
            userinfo_response = client.get(
                GOOGLE_USERINFO_URL,
                headers={
                    "Authorization": f"Bearer {access_token}"
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
    email_verified = google_user.get("email_verified")
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
    email = normalize_email(google_email)
    oauth_account = (
        db.query(OAuthAccount)
        .filter(
            OAuthAccount.provider == "google",
            OAuthAccount.provider_account_id == google_account_id,
        )
        .first()
    )
    if oauth_account is not None:
        user = db.get(User, oauth_account.user_id)
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
                    OAuthAccount.provider == "google",
                    OAuthAccount.provider_account_id == google_account_id,
                )
                .first()
            )
            if existing_account is None:
                raise HTTPException(
                    status_code=409,
                    detail="Unable to link Google account",
                )
            user = db.get(User, existing_account.user_id)
            if user is None:
                raise HTTPException(
                    status_code=500,
                    detail="OAuth account is linked to a missing user",
                )
    token = create_access_token(user.id)
    response = RedirectResponse(
        url=FRONTEND_URL,
        status_code=302,
    )
    set_auth_cookie(response, token)
    clear_google_oauth_state_cookie(response)
    return response
# ===================================================================
# GITHUB OAUTH
# ===================================================================
# -------------------------------------------------------------------
# GitHub login
# -------------------------------------------------------------------
@router.get("/github/login")
def github_login():
    if not GITHUB_CLIENT_ID:
        raise HTTPException(
            status_code=500,
            detail="GITHUB_CLIENT_ID is not configured",
        )
    if not GITHUB_REDIRECT_URI:
        raise HTTPException(
            status_code=500,
            detail="GITHUB_REDIRECT_URI is not configured",
        )
    state = secrets.token_urlsafe(32)
    # PKCE verifier/challenge.
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = create_pkce_code_challenge(code_verifier)
    params = {
        "client_id": GITHUB_CLIENT_ID,
        "redirect_uri": GITHUB_REDIRECT_URI,
        "scope": "user:email",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    authorization_url = (
        f"{GITHUB_AUTHORIZATION_URL}?{urlencode(params)}"
    )
    response = RedirectResponse(
        url=authorization_url,
        status_code=302,
    )
    set_github_oauth_state_cookie(response, state)
    set_github_code_verifier_cookie(response, code_verifier)
    return response
# -------------------------------------------------------------------
# GitHub callback
# -------------------------------------------------------------------
@router.get("/github/callback")
def github_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    github_oauth_state: str | None = Cookie(default=None),
    github_code_verifier: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
):
    if error:
        response = RedirectResponse(
            url=f"{FRONTEND_URL}/login?error=github_auth_denied",
            status_code=302,
        )
        clear_github_oauth_state_cookie(response)
        clear_github_code_verifier_cookie(response)
        return response
    if not code:
        raise HTTPException(
            status_code=400,
            detail="GitHub authorization code is missing",
        )
    if not state:
        raise HTTPException(
            status_code=400,
            detail="GitHub OAuth state is missing",
        )
    if not github_oauth_state:
        raise HTTPException(
            status_code=400,
            detail="GitHub OAuth state cookie is missing",
        )
    if not github_code_verifier:
        raise HTTPException(
            status_code=400,
            detail="GitHub PKCE verifier cookie is missing",
        )
    if not secrets.compare_digest(state, github_oauth_state):
        raise HTTPException(
            status_code=400,
            detail="Invalid GitHub OAuth state",
        )
    if not GITHUB_CLIENT_ID:
        raise HTTPException(
            status_code=500,
            detail="GITHUB_CLIENT_ID is not configured",
        )
    if not GITHUB_CLIENT_SECRET:
        raise HTTPException(
            status_code=500,
            detail="GITHUB_CLIENT_SECRET is not configured",
        )
    if not GITHUB_REDIRECT_URI:
        raise HTTPException(
            status_code=500,
            detail="GITHUB_REDIRECT_URI is not configured",
        )
    token_data = {
        "client_id": GITHUB_CLIENT_ID,
        "client_secret": GITHUB_CLIENT_SECRET,
        "code": code,
        "redirect_uri": GITHUB_REDIRECT_URI,
        "code_verifier": github_code_verifier,
    }
    try:
        with httpx.Client(timeout=10.0) as client:
            token_response = client.post(
                GITHUB_TOKEN_URL,
                data=token_data,
                headers={
                    "Accept": "application/json",
                },
            )
            token_response.raise_for_status()
            tokens = token_response.json()
            github_access_token = tokens.get("access_token")
            if not github_access_token:
                raise HTTPException(
                    status_code=400,
                    detail="GitHub did not return an access token",
                )
            api_headers = {
                "Authorization": f"Bearer {github_access_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
            user_response = client.get(
                GITHUB_USER_URL,
                headers=api_headers,
            )
            user_response.raise_for_status()
            github_user = user_response.json()
            emails_response = client.get(
                GITHUB_EMAILS_URL,
                headers=api_headers,
            )
            emails_response.raise_for_status()
            github_emails = emails_response.json()
    except httpx.HTTPError:
        raise HTTPException(
            status_code=502,
            detail="Failed to communicate with GitHub",
        )
    github_account_id = github_user.get("id")
    github_name = github_user.get("name") or github_user.get("login")
    if not github_account_id:
        raise HTTPException(
            status_code=400,
            detail="GitHub account ID is missing",
        )
    # Find the primary verified GitHub email.
    github_email = None
    for email_entry in github_emails:
        if (
            email_entry.get("primary") is True
            and email_entry.get("verified") is True
        ):
            github_email = email_entry.get("email")
            break
    # Fall back to any verified email if the primary one wasn't returned.
    if not github_email:
        for email_entry in github_emails:
            if email_entry.get("verified") is True:
                github_email = email_entry.get("email")
                break
    if not github_email:
        raise HTTPException(
            status_code=400,
            detail="No verified GitHub email address was found",
        )
    email = normalize_email(github_email)
    oauth_account = (
        db.query(OAuthAccount)
        .filter(
            OAuthAccount.provider == "github",
            OAuthAccount.provider_account_id == str(github_account_id),
        )
        .first()
    )
    if oauth_account is not None:
        user = db.get(User, oauth_account.user_id)
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
                name=github_name,
                password_hash=None,
            )
            db.add(user)
            db.flush()
        oauth_account = OAuthAccount(
            user_id=user.id,
            provider="github",
            provider_account_id=str(github_account_id),
        )
        db.add(oauth_account)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            existing_account = (
                db.query(OAuthAccount)
                .filter(
                    OAuthAccount.provider == "github",
                    OAuthAccount.provider_account_id == str(github_account_id),
                )
                .first()
            )
            if existing_account is None:
                raise HTTPException(
                    status_code=409,
                    detail="Unable to link GitHub account",
                )
            user = db.get(User, existing_account.user_id)
            if user is None:
                raise HTTPException(
                    status_code=500,
                    detail="OAuth account is linked to a missing user",
                )
    token = create_access_token(user.id)
    response = RedirectResponse(
        url=FRONTEND_URL,
        status_code=302,
    )
    set_auth_cookie(response, token)
    clear_github_oauth_state_cookie(response)
    clear_github_code_verifier_cookie(response)
    return response
