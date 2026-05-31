"""Per-user Google OAuth helpers for smart-reminder onboarding."""
from __future__ import annotations

import json
import os
from typing import Any

import requests

from src.scheduler import store as scheduler_store
from src.scheduler.google_client import (
    DEFAULT_AUTH_URI,
    DEFAULT_TOKEN_URI,
    GoogleCalendarConfigError,
    _import_google_deps,
)

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
]
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"


def redirect_uri(fallback: str | None = None) -> str:
    return (
        os.getenv("GOOGLE_OAUTH_REDIRECT_URI")
        or fallback
        or "http://localhost:5001/notify/onboarding/google/callback"
    )


def _client_config(current_redirect_uri: str | None = None) -> dict[str, Any]:
    secrets_path = os.getenv("GOOGLE_OAUTH_CLIENT_SECRETS_FILE")
    if secrets_path:
        try:
            return json.loads(open(secrets_path, "r", encoding="utf-8").read())
        except OSError as exc:
            raise GoogleCalendarConfigError(
                f"Could not read GOOGLE_OAUTH_CLIENT_SECRETS_FILE at {secrets_path}."
            ) from exc

    client_id = os.getenv("GOOGLE_OAUTH_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET")
    project_id = os.getenv("GOOGLE_OAUTH_PROJECT_ID", "ppt-smart-reminders")
    auth_uri = os.getenv("GOOGLE_OAUTH_AUTH_URI", DEFAULT_AUTH_URI)
    token_uri = os.getenv("GOOGLE_OAUTH_TOKEN_URI", DEFAULT_TOKEN_URI)

    if not client_id or not client_secret:
        stored = scheduler_store.get_google_oauth_client_config()
        if stored:
            return stored
        raise GoogleCalendarConfigError(
            "Google OAuth is not configured. Save the OAuth app credentials from "
            "the scheduler web UI or set GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET."
        )

    return {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "project_id": project_id,
            "auth_uri": auth_uri,
            "token_uri": token_uri,
            "redirect_uris": [redirect_uri(current_redirect_uri)],
        }
    }


def authorization_url(*, callback_url: str) -> tuple[str, str]:
    _, _, Flow, _ = _import_google_deps()
    flow = Flow.from_client_config(
        _client_config(callback_url),
        scopes=SCOPES,
        redirect_uri=redirect_uri(callback_url),
    )
    return flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )


def exchange_callback(*, full_callback_url: str, callback_url: str) -> dict[str, Any]:
    _, _, Flow, _ = _import_google_deps()
    flow = Flow.from_client_config(
        _client_config(callback_url),
        scopes=SCOPES,
        redirect_uri=redirect_uri(callback_url),
    )
    flow.fetch_token(authorization_response=full_callback_url)
    token_json = flow.credentials.to_json()
    user_info = fetch_user_info(flow.credentials.token)
    return {
        "token_json": token_json,
        "user_info": user_info,
        "scopes": list(SCOPES),
    }


def fetch_user_info(access_token: str) -> dict[str, Any]:
    response = requests.get(
        USERINFO_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    return {
        "sub": payload.get("sub"),
        "email": payload.get("email"),
        "name": payload.get("name") or payload.get("given_name") or payload.get("email"),
        "picture": payload.get("picture"),
    }
