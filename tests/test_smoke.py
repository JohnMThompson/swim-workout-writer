import pytest
from sqlalchemy import select

from swim_app import create_app
from swim_app.extensions import db
from swim_app.models import User


@pytest.fixture
def app(monkeypatch, tmp_path):
    monkeypatch.setattr("swim_app.load_dotenv", lambda *args, **kwargs: None)
    for key in (
        "DATABASE_URL",
        "ADMIN_USERNAME",
        "ADMIN_PASSWORD",
        "REQUIRE_DATABASE_URL",
        "INITIALIZE_DEFAULT_ADMIN",
    ):
        monkeypatch.delenv(key, raising=False)
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


def test_startup_preserves_existing_user_and_password(monkeypatch, tmp_path):
    monkeypatch.setattr("swim_app.load_dotenv", lambda *args, **kwargs: None)
    database_path = tmp_path / "existing.sqlite"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("ADMIN_USERNAME", "configured-admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "new-provisioning-password")
    locations_path = tmp_path / "canonical_locations.txt"
    locations_path.write_text("Minnetonka\n", encoding="utf-8")
    monkeypatch.setenv("CANONICAL_LOCATIONS_FILE", str(locations_path))

    first_app = create_app()
    with first_app.app_context():
        user = db.session.scalar(select(User).where(User.username == "configured-admin"))
        assert user is not None
        user.password_hash = User.create("configured-admin", "intentional-password").password_hash
        db.session.commit()

    second_app = create_app()
    with second_app.app_context():
        user = db.session.scalar(select(User).where(User.username == "configured-admin"))
        assert user is not None
        assert user.check_password("intentional-password")
        assert not user.check_password("new-provisioning-password")


def test_startup_creates_configured_admin_without_renaming_existing_user(monkeypatch, tmp_path):
    monkeypatch.setattr("swim_app.load_dotenv", lambda *args, **kwargs: None)
    database_path = tmp_path / "preserved.sqlite"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("ADMIN_USERNAME", "new-admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "initial-password")
    locations_path = tmp_path / "canonical_locations.txt"
    locations_path.write_text("Minnetonka\n", encoding="utf-8")
    monkeypatch.setenv("CANONICAL_LOCATIONS_FILE", str(locations_path))

    app = create_app()
    with app.app_context():
        existing_user = User.create("legacy-account", "legacy-password")
        db.session.add(existing_user)
        db.session.commit()

    app = create_app()
    with app.app_context():
        users = db.session.scalars(select(User).order_by(User.username)).all()
        assert [(user.username, user.check_password("legacy-password")) for user in users] == [
            ("legacy-account", True),
            ("new-admin", False),
        ]
        new_admin = next(user for user in users if user.username == "new-admin")
        assert new_admin.check_password("initial-password")


def test_startup_does_not_create_or_modify_users_when_admin_initialization_disabled(
    monkeypatch, tmp_path
):
    monkeypatch.setattr("swim_app.load_dotenv", lambda *args, **kwargs: None)
    database_path = tmp_path / "admin-init-disabled.sqlite"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("ADMIN_USERNAME", "configured-admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "provisioning-password")
    monkeypatch.setenv("INITIALIZE_DEFAULT_ADMIN", "false")
    locations_path = tmp_path / "canonical_locations.txt"
    locations_path.write_text("Minnetonka\n", encoding="utf-8")
    monkeypatch.setenv("CANONICAL_LOCATIONS_FILE", str(locations_path))

    app = create_app()
    with app.app_context():
        existing_user = User.create("existing-admin", "preserved-password")
        db.session.add(existing_user)
        db.session.commit()
        original_hash = existing_user.password_hash

    app = create_app()
    with app.app_context():
        users = db.session.scalars(select(User)).all()
        assert [(user.username, user.password_hash) for user in users] == [
            ("existing-admin", original_hash)
        ]
        assert users[0].check_password("preserved-password")
        assert not users[0].check_password("provisioning-password")


@pytest.mark.parametrize("database_url", [None, "", "   "])
def test_pileated_mode_requires_nonempty_database_url(monkeypatch, database_url):
    monkeypatch.setattr("swim_app.load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setenv("REQUIRE_DATABASE_URL", "true")
    if database_url is None:
        monkeypatch.delenv("DATABASE_URL", raising=False)
    else:
        monkeypatch.setenv("DATABASE_URL", database_url)

    with pytest.raises(RuntimeError, match="DATABASE_URL must be set"):
        create_app()
