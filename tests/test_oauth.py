from types import SimpleNamespace
from unittest.mock import MagicMock

from gateway.app import auth_routes
from gateway.app.main import app


class FakeResponse:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self.data


class FakeGoogleClient:
    def __init__(self, timeout=None):
        self.timeout = timeout

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def post(self, url, data, headers=None):
        return FakeResponse({"access_token": "fake-google-token"})

    def get(self, url, headers):
        return FakeResponse(
            {
                "sub": "google-account-123",
                "email": "existing@example.com",
                "name": "Google User",
                "email_verified": True,
            }
        )


class FakeUnverifiedGoogleClient(FakeGoogleClient):
    def get(self, url, headers):
        return FakeResponse(
            {
                "sub": "google-account-123",
                "email": "existing@example.com",
                "name": "Google User",
                "email_verified": False,
            }
        )


class FakeGitHubClient:
    def __init__(self, timeout=None):
        self.timeout = timeout

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def post(self, url, data, headers=None):
        return FakeResponse({"access_token": "fake-github-token"})

    def get(self, url, headers):
        if url == auth_routes.GITHUB_USER_URL:
            return FakeResponse(
                {
                    "id": 12345,
                    "login": "github-user",
                    "name": "GitHub User",
                }
            )

        if url == auth_routes.GITHUB_EMAILS_URL:
            return FakeResponse(
                [
                    {
                        "email": "existing@example.com",
                        "primary": True,
                        "verified": True,
                    }
                ]
            )

        raise AssertionError(f"Unexpected GitHub URL: {url}")


class FakeGitHubFallbackEmailClient(FakeGitHubClient):
    def get(self, url, headers):
        if url == auth_routes.GITHUB_USER_URL:
            return FakeResponse(
                {
                    "id": 12345,
                    "login": "github-user",
                    "name": "GitHub User",
                }
            )

        if url == auth_routes.GITHUB_EMAILS_URL:
            return FakeResponse(
                [
                    {
                        "email": "unverified@example.com",
                        "primary": True,
                        "verified": False,
                    },
                    {
                        "email": " Verified@Example.com ",
                        "primary": False,
                        "verified": True,
                    },
                ]
            )

        raise AssertionError(f"Unexpected GitHub URL: {url}")


def override_database(monkeypatch, db):
    def override_get_db():
        yield db

    monkeypatch.setitem(
        app.dependency_overrides,
        auth_routes.get_db,
        override_get_db,
    )


def configure_google_oauth(
    monkeypatch,
    client,
    fake_client=FakeGoogleClient,
):
    monkeypatch.setattr(auth_routes.httpx, "Client", fake_client)
    monkeypatch.setattr(auth_routes, "GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setattr(
        auth_routes,
        "GOOGLE_CLIENT_SECRET",
        "test-client-secret",
    )
    monkeypatch.setattr(
        auth_routes,
        "GOOGLE_REDIRECT_URI",
        "http://localhost:8000/auth/google/callback",
    )
    monkeypatch.setattr(
        auth_routes,
        "create_access_token",
        lambda user_id: "test-access-token",
    )

    client.cookies.set("google_oauth_state", "valid-test-state")


def configure_github_oauth(
    monkeypatch,
    client,
    fake_client=FakeGitHubClient,
):
    monkeypatch.setattr(auth_routes.httpx, "Client", fake_client)
    monkeypatch.setattr(auth_routes, "GITHUB_CLIENT_ID", "test-client-id")
    monkeypatch.setattr(
        auth_routes,
        "GITHUB_CLIENT_SECRET",
        "test-client-secret",
    )
    monkeypatch.setattr(
        auth_routes,
        "GITHUB_REDIRECT_URI",
        "http://localhost:8000/auth/github/callback",
    )
    monkeypatch.setattr(
        auth_routes,
        "create_access_token",
        lambda user_id: "test-access-token",
    )

    client.cookies.set("github_oauth_state", "valid-test-state")
    client.cookies.set("github_code_verifier", "test-code-verifier")


def make_existing_user():
    return SimpleNamespace(
        id="existing-user-id",
        email="existing@example.com",
        name="Existing User",
        password_hash="existing-password-hash",
        role="CUSTOMER",
    )


def make_query_result(result):
    query = MagicMock()
    query.filter.return_value.first.return_value = result
    return query


def test_google_oauth_rejects_automatic_linking_to_existing_user(
    client,
    monkeypatch,
):
    existing_user = make_existing_user()

    db = MagicMock()

    def mock_query(model):
        if model is auth_routes.OAuthAccount:
            return make_query_result(None)

        if model is auth_routes.User:
            return make_query_result(existing_user)

        raise AssertionError(f"Unexpected model: {model}")

    db.query.side_effect = mock_query

    override_database(monkeypatch, db)
    configure_google_oauth(monkeypatch, client)

    response = client.get(
        "/auth/google/callback",
        params={
            "code": "fake-authorization-code",
            "state": "valid-test-state",
        },
    )

    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]

    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_google_oauth_allows_sign_in_with_existing_linked_account(
    client,
    monkeypatch,
):
    existing_user = make_existing_user()

    linked_account = SimpleNamespace(
        user_id="existing-user-id",
    )

    db = MagicMock()
    db.query.return_value = make_query_result(linked_account)
    db.get.return_value = existing_user

    override_database(monkeypatch, db)
    configure_google_oauth(monkeypatch, client)

    response = client.get(
        "/auth/google/callback",
        params={
            "code": "fake-authorization-code",
            "state": "valid-test-state",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "location" in response.headers
    assert "set-cookie" in response.headers

    db.get.assert_called_once_with(
        auth_routes.User,
        "existing-user-id",
    )
    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_google_oauth_creates_new_account(
    client,
    monkeypatch,
):
    db = MagicMock()
    db.query.side_effect = [
        make_query_result(None),
        make_query_result(None),
    ]

    added_objects = []

    def mock_add(obj):
        if isinstance(obj, auth_routes.User) and not obj.id:
            obj.id = "new-google-user-id"

        added_objects.append(obj)

    db.add.side_effect = mock_add

    override_database(monkeypatch, db)
    configure_google_oauth(monkeypatch, client)

    response = client.get(
        "/auth/google/callback",
        params={
            "code": "fake-authorization-code",
            "state": "valid-test-state",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "set-cookie" in response.headers

    created_user = next(
        obj for obj in added_objects if isinstance(obj, auth_routes.User)
    )

    created_oauth_account = next(
        obj for obj in added_objects if isinstance(obj, auth_routes.OAuthAccount)
    )

    assert created_user.email == "existing@example.com"
    assert created_user.name == "Google User"
    assert created_user.password_hash is None

    assert created_oauth_account.provider == "google"
    assert created_oauth_account.provider_account_id == "google-account-123"

    db.flush.assert_called_once()
    db.commit.assert_called_once()


def test_google_oauth_rejects_unverified_email(
    client,
    monkeypatch,
):
    db = MagicMock()

    override_database(monkeypatch, db)
    configure_google_oauth(
        monkeypatch,
        client,
        FakeUnverifiedGoogleClient,
    )

    response = client.get(
        "/auth/google/callback",
        params={
            "code": "fake-authorization-code",
            "state": "valid-test-state",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Google email is not verified"

    db.query.assert_not_called()
    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_google_oauth_rejects_invalid_state(
    client,
    monkeypatch,
):
    db = MagicMock()

    override_database(monkeypatch, db)
    configure_google_oauth(monkeypatch, client)

    response = client.get(
        "/auth/google/callback",
        params={
            "code": "fake-authorization-code",
            "state": "wrong-test-state",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid Google OAuth state"

    db.query.assert_not_called()


def test_github_oauth_rejects_automatic_linking_to_existing_user(
    client,
    monkeypatch,
):
    existing_user = make_existing_user()

    db = MagicMock()
    db.query.side_effect = [
        make_query_result(None),
        make_query_result(existing_user),
    ]

    override_database(monkeypatch, db)
    configure_github_oauth(monkeypatch, client)

    response = client.get(
        "/auth/github/callback",
        params={
            "code": "fake-authorization-code",
            "state": "valid-test-state",
        },
    )

    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]

    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_github_oauth_allows_sign_in_with_existing_linked_account(
    client,
    monkeypatch,
):
    existing_user = make_existing_user()

    linked_account = SimpleNamespace(
        user_id="existing-user-id",
    )

    db = MagicMock()
    db.query.return_value = make_query_result(linked_account)
    db.get.return_value = existing_user

    override_database(monkeypatch, db)
    configure_github_oauth(monkeypatch, client)

    response = client.get(
        "/auth/github/callback",
        params={
            "code": "fake-authorization-code",
            "state": "valid-test-state",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "location" in response.headers
    assert "set-cookie" in response.headers

    db.get.assert_called_once_with(
        auth_routes.User,
        "existing-user-id",
    )
    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_github_oauth_uses_verified_fallback_email(
    client,
    monkeypatch,
):
    db = MagicMock()
    db.query.side_effect = [
        make_query_result(None),
        make_query_result(None),
    ]

    added_objects = []

    def mock_add(obj):
        if isinstance(obj, auth_routes.User) and not obj.id:
            obj.id = "new-github-user-id"

        added_objects.append(obj)

    db.add.side_effect = mock_add

    override_database(monkeypatch, db)
    configure_github_oauth(
        monkeypatch,
        client,
        FakeGitHubFallbackEmailClient,
    )

    response = client.get(
        "/auth/github/callback",
        params={
            "code": "fake-authorization-code",
            "state": "valid-test-state",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302

    created_user = next(
        obj for obj in added_objects if isinstance(obj, auth_routes.User)
    )

    created_oauth_account = next(
        obj for obj in added_objects if isinstance(obj, auth_routes.OAuthAccount)
    )

    assert created_user.email == "verified@example.com"
    assert created_user.name == "GitHub User"

    assert created_oauth_account.provider == "github"
    assert created_oauth_account.provider_account_id == "12345"

    db.flush.assert_called_once()
    db.commit.assert_called_once()
