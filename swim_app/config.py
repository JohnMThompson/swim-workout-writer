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
    WTF_CSRF_TIME_LIMIT = None
