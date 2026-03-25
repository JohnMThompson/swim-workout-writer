from __future__ import annotations

from datetime import date
from pathlib import Path
from uuid import uuid4

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.utils import secure_filename

from .extensions import db
from .forms import LoginForm, MappingForm, ReviewForm, UploadForm
from .models import StrokeMapping, UploadSession, User, Workout
from .parser import build_start_datetime, parse_workout

bp = Blueprint("main", __name__)
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg"}


@bp.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("main.upload"))
    return redirect(url_for("main.login"))


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.upload"))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and user.check_password(form.password.data):
            login_user(user)
            return redirect(url_for("main.upload"))
        flash("Invalid credentials.", "error")
    return render_template("login.html", form=form)


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    return redirect(url_for("main.login"))


@bp.route("/upload", methods=["GET", "POST"])
@login_required
def upload():
    form = UploadForm()
    if form.validate_on_submit():
        upload = form.screenshot.data
        ext = Path(upload.filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            flash("Only PNG and JPEG uploads are supported.", "error")
            return render_template("upload.html", form=form)
        filename = f"{uuid4().hex}_{secure_filename(upload.filename)}"
        destination = Path(bp.root_path).parent / "uploads" / filename
        upload.save(destination)

        parsed = parse_workout(destination, submission_date=date.today())
        session = UploadSession(image_filename=filename, extracted_payload=parsed.to_dict())
        db.session.add(session)
        db.session.commit()
        return redirect(url_for("main.review", upload_id=session.id))
    return render_template("upload.html", form=form)


@bp.route("/review/<int:upload_id>", methods=["GET", "POST"])
@login_required
def review(upload_id: int):
    upload_session = db.session.get(UploadSession, upload_id)
    if not upload_session:
        abort(404)
    payload = upload_session.extracted_payload
    review_form = ReviewForm(data=payload)
    review_form.upload_id.data = str(upload_session.id)
    mapping_forms = []
    for label in payload.get("unknown_strokes", []):
        form = MappingForm()
        form.source_label.data = label
        mapping_forms.append(form)

    duplicate_matches = _find_duplicate_workouts(payload)
    stroke_total = _sum_stroke_fields(payload)
    stroke_mismatch = (
        payload.get("total_distance_yards", 0) > 0
        and stroke_total != payload.get("total_distance_yards", 0)
    )

    if review_form.validate_on_submit():
        total_distance_yards = int(review_form.total_distance_yards.data)
        freestyle_distance = _optional_int(review_form.freestyle_distance.data) or 0
        breaststroke_distance = _optional_int(review_form.breaststroke_distance.data) or 0
        backstroke_distance = _optional_int(review_form.backstroke_distance.data) or 0
        butterfly_distance = _optional_int(review_form.butterfly_distance.data) or 0
        reviewed_stroke_total = (
            freestyle_distance
            + breaststroke_distance
            + backstroke_distance
            + butterfly_distance
        )
        reviewed_payload = {
            "workout_date": review_form.workout_date.data,
            "start_time": review_form.start_time.data,
            "location": review_form.location.data.strip(),
            "total_distance_yards": total_distance_yards,
            "duration": int(review_form.duration.data),
        }
        duplicate_matches = _find_duplicate_workouts(reviewed_payload)
        stroke_total = reviewed_stroke_total
        stroke_mismatch = (
            total_distance_yards > 0 and reviewed_stroke_total != total_distance_yards
        )

        if stroke_mismatch and not review_form.allow_stroke_mismatch.data:
            flash(
                "Stroke total does not equal total distance. Correct the values or check the override box.",
                "error",
            )
            return render_template(
                "review.html",
                form=review_form,
                upload_session=upload_session,
                mapping_forms=mapping_forms,
                unknown_strokes=payload.get("unknown_strokes", []),
                raw_strokes=payload.get("raw_strokes", []),
                duplicate_matches=duplicate_matches,
                stroke_total=stroke_total,
                stroke_mismatch=stroke_mismatch,
            )

        workout = Workout(
            start_date_time=build_start_datetime(
                review_form.workout_date.data, review_form.start_time.data
            ),
            duration=int(review_form.duration.data),
            total_distance_yards=total_distance_yards,
            location=review_form.location.data.strip(),
            comments=review_form.comments.data.strip() or None,
            freestyle_distance=freestyle_distance or None,
            breaststroke_distance=breaststroke_distance or None,
            backstroke_distance=backstroke_distance or None,
            butterfly_distance=butterfly_distance or None,
        )
        db.session.add(workout)
        db.session.delete(upload_session)
        db.session.commit()
        flash("Workout saved.", "success")
        return redirect(url_for("main.upload"))

    return render_template(
        "review.html",
        form=review_form,
        upload_session=upload_session,
        mapping_forms=mapping_forms,
        unknown_strokes=payload.get("unknown_strokes", []),
        raw_strokes=payload.get("raw_strokes", []),
        duplicate_matches=duplicate_matches,
        stroke_total=stroke_total,
        stroke_mismatch=stroke_mismatch,
    )


@bp.route("/stroke-mappings", methods=["POST"])
@login_required
def save_mapping():
    form = MappingForm()
    if form.validate_on_submit():
        source_label = form.source_label.data.strip().lower()
        mapping = StrokeMapping.query.filter_by(source_label=source_label).first()
        if not mapping:
            mapping = StrokeMapping(
                source_label=source_label, target_stroke=form.target_stroke.data
            )
            db.session.add(mapping)
        else:
            mapping.target_stroke = form.target_stroke.data
        db.session.commit()
        flash("Stroke mapping saved. Re-upload the screenshot to apply it.", "success")
    else:
        flash("Could not save stroke mapping.", "error")
    return redirect(request.referrer or url_for("main.upload"))


@bp.route("/uploads/<path:filename>")
@login_required
def uploaded_file(filename: str):
    return send_from_directory(Path(bp.root_path).parent / "uploads", filename)


def _optional_int(value: str | None) -> int | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    return int(stripped)


def _find_duplicate_workouts(payload: dict) -> list[Workout]:
    workout_date = payload.get("workout_date")
    start_time = payload.get("start_time")
    location = payload.get("location")
    total_distance_yards = payload.get("total_distance_yards")
    duration = payload.get("duration")

    if not all([workout_date, start_time, location, total_distance_yards, duration]):
        return []

    start_date_time = build_start_datetime(workout_date, start_time)
    return (
        Workout.query.filter_by(
            start_date_time=start_date_time,
            location=location,
            total_distance_yards=total_distance_yards,
            duration=duration,
        )
        .order_by(Workout.id.desc())
        .all()
    )


def _sum_stroke_fields(payload: dict) -> int:
    return sum(
        int(payload.get(field) or 0)
        for field in [
            "freestyle_distance",
            "breaststroke_distance",
            "backstroke_distance",
            "butterfly_distance",
        ]
    )
