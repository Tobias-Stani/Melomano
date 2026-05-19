import os
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from fastapi import Request

SECRET_KEY   = os.getenv("SECRET_KEY", "dev-secret-change-in-production")
APP_USERNAME = os.getenv("APP_USERNAME", "admin")
APP_PASSWORD = os.getenv("APP_PASSWORD", "admin")

COOKIE_NAME    = "melomano_session"
COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 dias

_signer = URLSafeTimedSerializer(SECRET_KEY)


def create_session_token(username: str) -> str:
    return _signer.dumps(username, salt="session")


def verify_session_token(token: str) -> str | None:
    try:
        return _signer.loads(token, salt="session", max_age=COOKIE_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None


def get_current_user(request: Request) -> str | None:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    return verify_session_token(token)


def check_credentials(username: str, password: str) -> bool:
    return username == APP_USERNAME and password == APP_PASSWORD
