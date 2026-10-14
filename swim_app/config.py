import os


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-me")
    DEBUG = os.environ.get("DEBUG", "false").lower() == "true"
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = 8 * 1024 * 1024
    UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", "uploads")
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "change-me-now")
    INITIALIZE_DEFAULT_ADMIN = os.environ.get("INITIALIZE_DEFAULT_ADMIN", "true").lower() == "true"
    AUTO_CREATE_SCHEMA = os.environ.get("AUTO_CREATE_SCHEMA")
    REQUIRE_DATABASE_URL = os.environ.get("REQUIRE_DATABASE_URL", "false").lower() == "true"
    INITIALIZE_DEFAULT_STROKE_MAPPINGS = (
        os.environ.get("INITIALIZE_DEFAULT_STROKE_MAPPINGS", "true").lower() == "true"
    )
    CANONICAL_LOCATIONS_FILE = os.environ.get("CANONICAL_LOCATIONS_FILE")
    WTF_CSRF_TIME_LIMIT = None
