from __future__ import annotations

import os
from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db, login_manager


class User(UserMixin, db.Model):
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

    @classmethod
    def default_username(cls) -> str:
        return os.environ.get("ADMIN_USERNAME", "admin")

    @classmethod
    def default_password(cls) -> str:
        return os.environ.get("ADMIN_PASSWORD", "change-me-now")

    @classmethod
    def create(cls, username: str, password: str) -> "User":
        return cls(username=username, password_hash=generate_password_hash(password))

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


@login_manager.user_loader
def load_user(user_id: str) -> User | None:
    return db.session.get(User, int(user_id))


class StrokeMapping(db.Model):
    __tablename__ = "stroke_mapping"

    id = db.Column(db.Integer, primary_key=True)
    source_label = db.Column(db.String(255), unique=True, nullable=False)
    target_stroke = db.Column(db.String(32), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class Workout(db.Model):
    __tablename__ = "swim_tracking"

    id = db.Column(db.Integer, primary_key=True)
    start_date_time = db.Column(db.DateTime, nullable=False)
    duration = db.Column(db.Integer, nullable=False)
    total_distance_yards = db.Column(db.Integer, nullable=False)
    location = db.Column(db.String(255), nullable=False)
    comments = db.Column(db.Text, nullable=True)
    freestyle_distance = db.Column(db.Integer, nullable=True)
    breaststroke_distance = db.Column(db.Integer, nullable=True)
    backstroke_distance = db.Column(db.Integer, nullable=True)
    butterfly_distance = db.Column(db.Integer, nullable=True)


class UploadSession(db.Model):
    __tablename__ = "upload_session"

    id = db.Column(db.Integer, primary_key=True)
    image_filename = db.Column(db.String(255), nullable=False)
    extracted_payload = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
