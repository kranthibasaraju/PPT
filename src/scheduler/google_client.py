"""Google Calendar OAuth and API wrapper for the PPT scheduler."""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any

from src.scheduler import store

log = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
]
DEFAULT_AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
DEFAULT_TOKEN_URI = "https://oauth2.googleapis.com/token"


class GoogleCalendarError(RuntimeError):
    """Base exception for Google Calendar integration failures."""


class GoogleCalendarConfigError(GoogleCalendarError):
    """Raised when OAuth/client configuration is missing."""


def _import_google_deps():
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import Flow
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise GoogleCalendarConfigError(
            "Google Calendar dependencies are not installed. "
            "Add google-api-python-client, google-auth, and google-auth-oauthlib."
        ) from exc
    return Request, Credentials, Flow, build


@dataclass
class CalendarApiClient:
    """Small wrapper around Google OAuth credentials and Calendar API calls."""

    scopes: list[str] = None

    def __post_init__(self) -> None:
        if self.scopes is None:
            self.scopes = list(SCOPES)

    def status(self) -> dict[str, Any]:
        config_source = self.config_source()
        return {
            "configured": config_source != "none",
            "connected": self.is_connected(),
            "config_source": config_source,
            "redirect_uri": self.redirect_uri(None),
            "scopes": list(self.scopes),
            "token_path": str(store.token_path()),
        }

    def config_source(self) -> str:
        if os.getenv("GOOGLE_OAUTH_CLIENT_SECRETS_FILE"):
            return "env_file"
        if os.getenv("GOOGLE_OAUTH_CLIENT_ID") and os.getenv("GOOGLE_OAUTH_CLIENT_SECRET"):
            return "env_vars"
        if store.get_google_oauth_client_config():
            return "web"
        return "none"

    def is_configured(self) -> bool:
        try:
            self._client_config()
        except GoogleCalendarConfigError:
            return False
        return True

    def is_connected(self) -> bool:
        try:
            return self.credentials() is not None
        except GoogleCalendarError:
            return False

    def redirect_uri(self, fallback: str | None) -> str:
        return (
            os.getenv("GOOGLE_OAUTH_REDIRECT_URI")
            or fallback
            or "http://localhost:5001/scheduler/oauth/callback"
        )

    def authorization_url(self, *, redirect_uri: str) -> tuple[str, str]:
        _, _, Flow, _ = _import_google_deps()
        flow = Flow.from_client_config(
            self._client_config(),
            scopes=self.scopes,
            redirect_uri=self.redirect_uri(redirect_uri),
        )
        url, state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )
        return url, state

    def exchange_callback(self, *, full_callback_url: str, redirect_uri: str) -> None:
        _, _, Flow, _ = _import_google_deps()
        flow = Flow.from_client_config(
            self._client_config(),
            scopes=self.scopes,
            redirect_uri=self.redirect_uri(redirect_uri),
        )
        flow.fetch_token(authorization_response=full_callback_url)
        self._save_credentials(flow.credentials)

    def disconnect(self) -> None:
        store.clear_token()

    def credentials(self):
        Request, Credentials, _, _ = _import_google_deps()
        token_json = store.load_token_json()
        if not token_json:
            return None
        creds = Credentials.from_authorized_user_info(json.loads(token_json), self.scopes)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            self._save_credentials(creds)
        return creds

    def service(self):
        _, _, _, build = _import_google_deps()
        creds = self.credentials()
        if creds is None:
            raise GoogleCalendarConfigError("Google Calendar is not connected.")
        return build("calendar", "v3", credentials=creds, cache_discovery=False)

    def list_calendars(self) -> list[dict[str, Any]]:
        service = self.service()
        page_token = None
        items: list[dict[str, Any]] = []
        while True:
            result = (
                service.calendarList()
                .list(pageToken=page_token, maxResults=250)
                .execute()
            )
            items.extend(result.get("items", []))
            page_token = result.get("nextPageToken")
            if not page_token:
                break
        return items

    def list_events(
        self,
        calendar_id: str,
        *,
        time_min: str,
        time_max: str,
        single_events: bool = True,
        max_results: int = 250,
    ) -> list[dict[str, Any]]:
        service = self.service()
        result = (
            service.events()
            .list(
                calendarId=calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=single_events,
                orderBy="startTime" if single_events else None,
                showDeleted=False,
                maxResults=max_results,
            )
            .execute()
        )
        return result.get("items", [])

    def get_event(self, calendar_id: str, event_id: str) -> dict[str, Any]:
        service = self.service()
        return (
            service.events()
            .get(calendarId=calendar_id, eventId=event_id)
            .execute()
        )

    def insert_event(self, calendar_id: str, body: dict[str, Any]) -> dict[str, Any]:
        service = self.service()
        return (
            service.events()
            .insert(calendarId=calendar_id, body=body)
            .execute()
        )

    def update_event(self, calendar_id: str, event_id: str, body: dict[str, Any]) -> dict[str, Any]:
        service = self.service()
        return (
            service.events()
            .update(calendarId=calendar_id, eventId=event_id, body=body)
            .execute()
        )

    def delete_event(self, calendar_id: str, event_id: str) -> None:
        service = self.service()
        service.events().delete(calendarId=calendar_id, eventId=event_id).execute()

    def _save_credentials(self, credentials) -> None:
        store.save_token_json(credentials.to_json())

    def _client_config(self) -> dict[str, Any]:
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
        project_id = os.getenv("GOOGLE_OAUTH_PROJECT_ID", "ppt-scheduler")
        auth_uri = os.getenv("GOOGLE_OAUTH_AUTH_URI", DEFAULT_AUTH_URI)
        token_uri = os.getenv("GOOGLE_OAUTH_TOKEN_URI", DEFAULT_TOKEN_URI)

        if not client_id or not client_secret:
            stored_config = store.get_google_oauth_client_config()
            if stored_config:
                return stored_config
            raise GoogleCalendarConfigError(
                "Google OAuth is not configured. Set GOOGLE_OAUTH_CLIENT_ID and "
                "GOOGLE_OAUTH_CLIENT_SECRET, point GOOGLE_OAUTH_CLIENT_SECRETS_FILE "
                "at an untracked client secrets JSON file, or save the OAuth app credentials from the scheduler web UI."
            )

        return {
            "web": {
                "client_id": client_id,
                "client_secret": client_secret,
                "project_id": project_id,
                "auth_uri": auth_uri,
                "token_uri": token_uri,
                "redirect_uris": [self.redirect_uri(None)],
            }
        }
