import pytest

from swim_app import create_app


@pytest.fixture
def app(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("ADMIN_USERNAME", "tester")
    monkeypatch.setenv("ADMIN_PASSWORD", "secret-pass")
    locations_path = tmp_path / "canonical_locations.txt"
    locations_path.write_text("Minnetonka\n", encoding="utf-8")
    monkeypatch.setenv("CANONICAL_LOCATIONS_FILE", str(locations_path))
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    yield app


@pytest.fixture
def client(app):
    return app.test_client()


def test_healthz_returns_ok(client):
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_login_page_loads(client):
    response = client.get("/login")

    assert response.status_code == 200
    assert b"Username" in response.data
    assert b"Password" in response.data


def test_valid_login_succeeds(client):
    response = client.post(
        "/login",
        data={"username": "tester", "password": "secret-pass"},
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/upload"
