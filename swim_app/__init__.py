from pathlib import Path
import os

from flask import Flask
from dotenv import load_dotenv
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from .extensions import csrf, db, login_manager
from .locations import get_canonical_locations
from .models import StrokeMapping, UploadSession, User, Workout
from .config import Config


def create_app() -> Flask:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY", "change-me"),
        DEBUG=os.environ.get("DEBUG", "false").lower() == "true",
        SESSION_COOKIE_SECURE=(
            os.environ.get("SESSION_COOKIE_SECURE", "false").lower() == "true"
        ),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SQLALCHEMY_DATABASE_URI=os.environ.get("DATABASE_URL"),
        UPLOAD_FOLDER=os.environ.get("UPLOAD_FOLDER", "uploads"),
        ADMIN_USERNAME=os.environ.get("ADMIN_USERNAME", "admin"),
        ADMIN_PASSWORD=os.environ.get("ADMIN_PASSWORD", "change-me-now"),
        INITIALIZE_DEFAULT_ADMIN=(
            os.environ.get("INITIALIZE_DEFAULT_ADMIN", "true").lower() == "true"
        ),
        AUTO_CREATE_SCHEMA=os.environ.get("AUTO_CREATE_SCHEMA"),
        REQUIRE_DATABASE_URL=os.environ.get("REQUIRE_DATABASE_URL", "false").lower() == "true",
        INITIALIZE_DEFAULT_STROKE_MAPPINGS=(
            os.environ.get("INITIALIZE_DEFAULT_STROKE_MAPPINGS", "true").lower() == "true"
        ),
        CANONICAL_LOCATIONS_FILE=os.environ.get("CANONICAL_LOCATIONS_FILE"),
    )
    if app.config.get("REQUIRE_DATABASE_URL") and not (app.config.get("SQLALCHEMY_DATABASE_URI") or "").strip():
        raise RuntimeError("DATABASE_URL must be set for this deployment.")
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    app.config["SQLALCHEMY_DATABASE_URI"] = _normalize_database_uri(
        app.config.get("SQLALCHEMY_DATABASE_URI"), app.instance_path
    )
    if app.config.get("REQUIRE_DATABASE_URL") and _should_auto_create_schema(app):
        raise RuntimeError("AUTO_CREATE_SCHEMA must be false for this deployment.")

    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    from .routes import bp

    app.register_blueprint(bp)

    with app.app_context():
        if _should_auto_create_schema(app):
            db.create_all()
        else:
            _validate_required_tables()
        if app.config.get("INITIALIZE_DEFAULT_ADMIN", True):
            _ensure_default_admin()
        if app.config.get("INITIALIZE_DEFAULT_STROKE_MAPPINGS", True):
            _ensure_default_stroke_mappings()
        _ensure_canonical_locations_file()

    return app


def _ensure_default_admin() -> None:
    username = User.default_username()
    password = User.default_password()
    existing = User.query.filter_by(username=username).first()
    if existing:
        return
    db.session.add(User.create(username=username, password=password))
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()


def _ensure_default_stroke_mappings() -> None:
    defaults = {
        "freestyle": "freestyle",
        "breaststroke": "breaststroke",
        "backstroke": "backstroke",
        "butterfly": "butterfly",
        "kickboard": "freestyle",
    }
    for source_label, target_stroke in defaults.items():
        existing = StrokeMapping.query.filter_by(source_label=source_label).first()
        if existing:
            continue
        db.session.add(
            StrokeMapping(source_label=source_label, target_stroke=target_stroke)
        )
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()


def _ensure_canonical_locations_file() -> None:
    get_canonical_locations()


def _normalize_database_uri(database_uri: str | None, instance_path: str) -> str:
    if not database_uri:
        return "sqlite:///" + str(Path(instance_path) / "swim_workouts.db")

    sqlite_prefix = "sqlite:///"
    if not database_uri.startswith(sqlite_prefix):
        return database_uri

    sqlite_target = database_uri[len(sqlite_prefix):]
    if sqlite_target == ":memory:":
        return database_uri
    if sqlite_target.startswith("/"):
        return database_uri

    absolute_target = Path.cwd() / sqlite_target
    absolute_target.parent.mkdir(parents=True, exist_ok=True)
    return sqlite_prefix + str(absolute_target)


def _should_auto_create_schema(app: Flask) -> bool:
    configured = app.config.get("AUTO_CREATE_SCHEMA")
    if configured is not None:
        return str(configured).lower() == "true"

    database_uri = app.config["SQLALCHEMY_DATABASE_URI"]
    return database_uri.startswith("sqlite:///") or database_uri == "sqlite:///:memory:"


def _validate_required_tables() -> None:
    inspector = inspect(db.engine)
    existing_tables = set(inspector.get_table_names())
    required_tables = {
        User.__tablename__,
        StrokeMapping.__tablename__,
        UploadSession.__tablename__,
        Workout.__tablename__,
    }
    missing_tables = sorted(required_tables - existing_tables)
    if missing_tables:
        raise RuntimeError(
            "Missing required tables for production startup: "
            + ", ".join(missing_tables)
            + ". Set AUTO_CREATE_SCHEMA=true only if you intentionally want the app to create them."
        )
