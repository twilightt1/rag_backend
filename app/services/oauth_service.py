"""Google OAuth 2.0 via Authlib."""
from authlib.integrations.httpx_client import AsyncOAuth2Client
from app.config import settings

GOOGLE_AUTH_URL  = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO  = "https://openidconnect.googleapis.com/v1/userinfo"


class GoogleOAuthService:
    @property
    def _redirect_uri(self) -> str:
        return f"{settings.API_BASE_URL}/api/v1/auth/google/callback"

    def _client(self) -> AsyncOAuth2Client:
        return AsyncOAuth2Client(
            client_id=settings.GOOGLE_CLIENT_ID,
            client_secret=settings.GOOGLE_CLIENT_SECRET,
            redirect_uri=self._redirect_uri,
        )

    def create_authorization_url(self) -> tuple[str, str]:
        client = self._client()
        return client.create_authorization_url(
            GOOGLE_AUTH_URL,
            scope="openid email profile",
            access_type="offline",
            prompt="select_account",
        )

    async def exchange_code(self, code: str) -> dict:
        """Exchange authorization code for user info. Returns {sub, email, name, picture}."""
        async with self._client() as client:
            token = await client.fetch_token(
                GOOGLE_TOKEN_URL,
                code=code,
                redirect_uri=self._redirect_uri,
            )
            resp = await client.get(GOOGLE_USERINFO, token=token)
            resp.raise_for_status()
            return resp.json()


google_oauth = GoogleOAuthService()
