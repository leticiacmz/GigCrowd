from app.core.logger import get_logger

logger = get_logger("spotify_auth")


class SpotifyAuth:

    def generate_auth_url(self):
        logger.info("Generating Spotify OAuth URL (PKCE placeholder)")
        return "https://accounts.spotify.com/authorize"

    def exchange_code(self, code: str):
        logger.info("Exchanging Spotify auth code (stub)")
        return {
            "access_token": "mock",
            "refresh_token": "mock"
        }