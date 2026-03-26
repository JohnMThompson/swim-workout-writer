from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from uuid import uuid4
import os

from flask import (
    Blueprint,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import func
from werkzeug.utils import secure_filename

from .extensions import db
from .forms import (
    DeleteWorkoutForm,
    EditWorkoutForm,
    LoginForm,
    MappingForm,
    ReviewForm,
    UploadForm,
    WorkoutFilterForm,
)
from .models import StrokeMapping, UploadSession, User, Workout
from .parser import build_start_datetime, parse_workout

bp = Blueprint("main", __name__)
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg"}


@bp.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("main.upload"))
    return redirect(url_for("main.login"))


@bp.route("/healthz")
def healthz():
    return jsonify({"status": "ok"})


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
    stroke_mismatch = _has_stroke_mismatch(payload, stroke_total)

    if review_form.validate_on_submit():
        workout_data = _extract_workout_form_data(review_form)
        duplicate_matches = _find_duplicate_workouts(workout_data)
        stroke_total = workout_data["stroke_total"]
        stroke_mismatch = workout_data["stroke_mismatch"]

        if stroke_mismatch and not review_form.allow_stroke_mismatch.data:
            return _render_review_template(
                review_form,
                upload_session,
                payload,
                mapping_forms,
                duplicate_matches,
                stroke_total,
                stroke_mismatch,
                flash_mismatch=True,
            )

        workout = Workout()
        _apply_workout_data(workout, workout_data)
        db.session.add(workout)
        db.session.delete(upload_session)
        db.session.commit()
        _delete_uploaded_file(upload_session.image_filename)
        flash("Workout saved.", "success")
        return redirect(url_for("main.upload"))

    return _render_review_template(
        review_form,
        upload_session,
        payload,
        mapping_forms,
        duplicate_matches,
        stroke_total,
        stroke_mismatch,
    )


@bp.route("/workouts", methods=["GET"])
@login_required
def manage_workouts():
    form = WorkoutFilterForm(formdata=request.args)
    workouts = _query_workouts(form)
    return render_template(
        "manage_workouts.html",
        form=form,
        workouts=workouts,
        active_filters=_workout_filter_query_params(form),
    )


@bp.route("/workouts/<int:workout_id>/edit", methods=["GET", "POST"])
@login_required
def edit_workout(workout_id: int):
    workout = db.session.get(Workout, workout_id)
    if not workout:
        abort(404)

    form = EditWorkoutForm(data=_workout_to_form_data(workout))
    duplicate_matches = _find_duplicate_workouts(_workout_to_duplicate_payload(workout), workout.id)
    stroke_total = _sum_stroke_fields(_workout_to_form_data(workout))
    stroke_mismatch = _has_stroke_mismatch(_workout_to_form_data(workout), stroke_total)

    if form.validate_on_submit():
        workout_data = _extract_workout_form_data(form)
        duplicate_matches = _find_duplicate_workouts(workout_data, workout.id)
        stroke_total = workout_data["stroke_total"]
        stroke_mismatch = workout_data["stroke_mismatch"]

        if stroke_mismatch and not form.allow_stroke_mismatch.data:
            flash(
                "Stroke total does not equal total distance. Correct the values or check the override box.",
                "error",
            )
            return render_template(
                "edit_workout.html",
                form=form,
                workout=workout,
                duplicate_matches=duplicate_matches,
                stroke_total=stroke_total,
                stroke_mismatch=stroke_mismatch,
            )

        _apply_workout_data(workout, workout_data)
        db.session.commit()
        flash("Workout updated.", "success")
        return redirect(url_for("main.manage_workouts"))

    return render_template(
        "edit_workout.html",
        form=form,
        workout=workout,
        duplicate_matches=duplicate_matches,
        stroke_total=stroke_total,
        stroke_mismatch=stroke_mismatch,
    )


@bp.route("/workouts/<int:workout_id>/delete", methods=["GET", "POST"])
@login_required
def delete_workout(workout_id: int):
    workout = db.session.get(Workout, workout_id)
    if not workout:
        abort(404)

    form = DeleteWorkoutForm()
    if form.validate_on_submit():
        db.session.delete(workout)
        db.session.commit()
        flash("Workout deleted.", "success")
        return redirect(url_for("main.manage_workouts"))

    return render_template("delete_workout.html", form=form, workout=workout)


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


def _render_review_template(
    form: ReviewForm,
    upload_session: UploadSession,
    payload: dict,
    mapping_forms: list[MappingForm],
    duplicate_matches: list[Workout],
    stroke_total: int,
    stroke_mismatch: bool,
    flash_mismatch: bool = False,
):
    if stroke_mismatch and flash_mismatch:
        flash(
            "Stroke total does not equal total distance. Correct the values or check the override box.",
            "error",
        )
    return render_template(
        "review.html",
        form=form,
        upload_session=upload_session,
        mapping_forms=mapping_forms,
        unknown_strokes=payload.get("unknown_strokes", []),
        raw_strokes=payload.get("raw_strokes", []),
        duplicate_matches=duplicate_matches,
        stroke_total=stroke_total,
        stroke_mismatch=stroke_mismatch,
    )


def _extract_workout_form_data(form) -> dict:
    total_distance_yards = int(form.total_distance_yards.data)
    freestyle_distance = _optional_int(form.freestyle_distance.data) or 0
    breaststroke_distance = _optional_int(form.breaststroke_distance.data) or 0
    backstroke_distance = _optional_int(form.backstroke_distance.data) or 0
    butterfly_distance = _optional_int(form.butterfly_distance.data) or 0
    stroke_total = (
        freestyle_distance
        + breaststroke_distance
        + backstroke_distance
        + butterfly_distance
    )
    payload = {
        "workout_date": form.workout_date.data,
        "start_time": form.start_time.data,
        "end_time": form.end_time.data,
        "location": form.location.data.strip(),
        "total_distance_yards": total_distance_yards,
        "duration": int(form.duration.data),
        "comments": form.comments.data.strip() or None,
        "freestyle_distance": freestyle_distance,
        "breaststroke_distance": breaststroke_distance,
        "backstroke_distance": backstroke_distance,
        "butterfly_distance": butterfly_distance,
        "stroke_total": stroke_total,
        "stroke_mismatch": total_distance_yards > 0 and stroke_total != total_distance_yards,
    }
    return payload


def _apply_workout_data(workout: Workout, payload: dict) -> None:
    workout.start_date_time = build_start_datetime(
        payload["workout_date"], payload["start_time"]
    )
    workout.duration = payload["duration"]
    workout.total_distance_yards = payload["total_distance_yards"]
    workout.location = payload["location"]
    workout.comments = payload["comments"]
    workout.freestyle_distance = payload["freestyle_distance"] or None
    workout.breaststroke_distance = payload["breaststroke_distance"] or None
    workout.backstroke_distance = payload["backstroke_distance"] or None
    workout.butterfly_distance = payload["butterfly_distance"] or None


def _workout_to_form_data(workout: Workout) -> dict:
    return {
        "workout_date": workout.start_date_time.strftime("%Y-%m-%d"),
        "start_time": workout.start_date_time.strftime("%H:%M"),
        "end_time": _format_end_time(workout.start_date_time, workout.duration),
        "duration": str(workout.duration),
        "total_distance_yards": str(workout.total_distance_yards),
        "location": workout.location,
        "comments": workout.comments or "",
        "freestyle_distance": _stringify_optional_int(workout.freestyle_distance),
        "breaststroke_distance": _stringify_optional_int(workout.breaststroke_distance),
        "backstroke_distance": _stringify_optional_int(workout.backstroke_distance),
        "butterfly_distance": _stringify_optional_int(workout.butterfly_distance),
    }


def _workout_to_duplicate_payload(workout: Workout) -> dict:
    return {
        "workout_date": workout.start_date_time.strftime("%Y-%m-%d"),
        "start_time": workout.start_date_time.strftime("%H:%M"),
        "location": workout.location,
        "total_distance_yards": workout.total_distance_yards,
        "duration": workout.duration,
    }


def _query_workouts(form: WorkoutFilterForm) -> list[Workout]:
    query = Workout.query
    days = _parse_days(form.days.data)
    if days is not None:
        cutoff = datetime.combine(date.today() - timedelta(days=days - 1), datetime.min.time())
        query = query.filter(Workout.start_date_time >= cutoff)
    return query.order_by(Workout.start_date_time.desc()).all()


def _workout_filter_query_params(form: WorkoutFilterForm) -> dict:
    return {"days": form.days.data if _parse_days(form.days.data) is None else str(_parse_days(form.days.data))}


def _optional_int(value: str | None) -> int | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    return int(stripped)


def _find_duplicate_workouts(payload: dict, exclude_workout_id: int | None = None) -> list[Workout]:
    workout_date = payload.get("workout_date")
    start_time = payload.get("start_time")
    location = payload.get("location")
    total_distance_yards = payload.get("total_distance_yards")
    duration = payload.get("duration")

    if not all([workout_date, start_time, location, total_distance_yards, duration]):
        return []

    start_date_time = build_start_datetime(workout_date, start_time)
    query = Workout.query.filter_by(
        start_date_time=start_date_time,
        location=location,
        total_distance_yards=total_distance_yards,
        duration=duration,
    )
    if exclude_workout_id is not None:
        query = query.filter(Workout.id != exclude_workout_id)
    return query.order_by(Workout.id.desc()).all()


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


def _has_stroke_mismatch(payload: dict, stroke_total: int) -> bool:
    total_distance_yards = int(payload.get("total_distance_yards") or 0)
    return total_distance_yards > 0 and stroke_total != total_distance_yards


def _parse_days(raw_days: str | None) -> int | None:
    if raw_days == "all":
        return None
    allowed_days = {7, 14, 30, 90, 365}
    try:
        days = int(raw_days or 7)
    except ValueError:
        return 7
    return days if days in allowed_days else 7


def _stringify_optional_int(value: int | None) -> str:
    if value is None:
        return ""
    return str(value)


def _format_end_time(start_date_time: datetime, duration_minutes: int) -> str:
    end_time = start_date_time + timedelta(minutes=duration_minutes)
    return end_time.strftime("%H:%M")


def _delete_uploaded_file(filename: str) -> None:
    path = Path(bp.root_path).parent / "uploads" / filename
    try:
        os.remove(path)
    except FileNotFoundError:
        return
