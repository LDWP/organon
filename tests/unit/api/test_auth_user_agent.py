"""Le callback OAuth s'identifie auprès de Wikimedia avec le User-Agent d'Organon."""

from organon.api.routes.auth import _oauth_client
from organon.core.auth_settings import AuthSettings
from organon.core.http import USER_AGENT


def test_oauth_client_sends_organon_user_agent():
    client = _oauth_client(AuthSettings(oauth_client_id="id", oauth_client_secret="s"))
    assert client.headers["User-Agent"] == USER_AGENT
