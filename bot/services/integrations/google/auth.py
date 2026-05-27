from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

from bot.config import settings

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def _client_config() -> dict[str, object]:
    return {
        "web": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uris": [f"https://{settings.webhook_domain}/oauth/google/callback"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }


def get_authorization_url(state: str) -> str:
    flow = Flow.from_client_config(_client_config(), scopes=SCOPES)
    flow.redirect_uri = f"https://{settings.webhook_domain}/oauth/google/callback"
    url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        state=state,
        prompt="consent",
    )
    return url


def exchange_code(code: str) -> dict[str, object]:
    flow = Flow.from_client_config(_client_config(), scopes=SCOPES)
    flow.redirect_uri = f"https://{settings.webhook_domain}/oauth/google/callback"
    flow.fetch_token(code=code)
    creds = flow.credentials
    return _creds_to_dict(creds)


def refresh_token(credentials_dict: dict[str, object]) -> dict[str, object]:
    creds = Credentials(
        token=str(credentials_dict.get("token", "")),
        refresh_token=str(credentials_dict.get("refresh_token", "")),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
    )
    import google.auth.transport.requests

    request = google.auth.transport.requests.Request()
    creds.refresh(request)
    return _creds_to_dict(creds)


def _creds_to_dict(creds: Credentials) -> dict[str, object]:
    return {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes or []),
    }
