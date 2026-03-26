from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from swim_app import create_app
from swim_app.extensions import db
from swim_app.models import UploadSession, Workout
from swim_app.parser import parse_workout
from swim_app.routes import _find_duplicate_workouts, _sum_stroke_fields


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("ADMIN_USERNAME", "tester")
    monkeypatch.setenv("ADMIN_PASSWORD", "secret-pass")
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    yield app


@pytest.fixture
def client(app):
    return app.test_client()


def login(client):
    return client.post(
        "/login",
        data={"username": "tester", "password": "secret-pass"},
        follow_redirects=True,
    )


def create_workout(
    *,
    start_date_time=datetime(2026, 3, 24, 16, 45),
    duration=30,
    total_distance_yards=736,
    location="Minnetonka",
    comments=None,
    freestyle_distance=598,
    breaststroke_distance=138,
    backstroke_distance=None,
    butterfly_distance=None,
):
    workout = Workout(
        start_date_time=start_date_time,
        duration=duration,
        total_distance_yards=total_distance_yards,
        location=location,
        comments=comments,
        freestyle_distance=freestyle_distance,
        breaststroke_distance=breaststroke_distance,
        backstroke_distance=backstroke_distance,
        butterfly_distance=butterfly_distance,
    )
    db.session.add(workout)
    db.session.commit()
    return workout


def test_parse_sample_workout(app):
    with app.app_context():
        result = parse_workout(
            "samples/workouts/IMG_3250.PNG", submission_date=date(2026, 3, 25)
        )

    assert result.workout_date == "2026-03-24"
    assert result.start_time == "16:45"
    assert result.end_time == "17:15"
    assert result.duration == 30
    assert result.total_distance_yards == 736
    assert result.location == "Minnetonka"
    assert result.freestyle_distance == 598
    assert result.breaststroke_distance == 138


def test_parse_total_distance_ignores_pool_length_when_ocr_distorts_distance_suffix(app):
    with app.app_context():
        result = parse_workout(
            "samples/workouts/IMG_3253.PNG", submission_date=date(2026, 3, 25)
        )

    assert result.total_distance_yards == 650
    assert result.freestyle_distance == 650


def test_parse_total_distance_can_fall_back_to_stroke_sum(app):
    with app.app_context():
        result = parse_workout(
            "samples/workouts/IMG_3255.PNG", submission_date=date(2026, 3, 25)
        )

    assert result.total_distance_yards == 550
    assert result.freestyle_distance == 550


def test_find_duplicate_workouts_matches_existing_row(app):
    with app.app_context():
        create_workout()

        matches = _find_duplicate_workouts(
            {
                "workout_date": "2026-03-24",
                "start_time": "16:45",
                "location": "Minnetonka",
                "total_distance_yards": 736,
                "duration": 30,
            }
        )

    assert len(matches) == 1
    assert matches[0].location == "Minnetonka"


def test_sum_stroke_fields_adds_all_strokes():
    total = _sum_stroke_fields(
        {
            "freestyle_distance": 100,
            "breaststroke_distance": 50,
            "backstroke_distance": 25,
            "butterfly_distance": 25,
        }
    )

    assert total == 200


def test_review_blocks_save_when_stroke_total_mismatches_without_override(app, client):
    login(client)

    with app.app_context():
        session = UploadSession(
            image_filename="fake.png",
            extracted_payload={
                "workout_date": "2026-03-24",
                "start_time": "16:45",
                "end_time": "17:15",
                "duration": 30,
                "total_distance_yards": 736,
                "location": "Minnetonka",
                "comments": "",
                "freestyle_distance": 500,
                "breaststroke_distance": 100,
                "backstroke_distance": 0,
                "butterfly_distance": 0,
                "raw_strokes": [],
                "unknown_strokes": [],
                "ocr_text": "",
            },
        )
        db.session.add(session)
        db.session.commit()
        upload_id = session.id

    response = client.post(
        f"/review/{upload_id}",
        data={
            "upload_id": str(upload_id),
            "workout_date": "2026-03-24",
            "start_time": "16:45",
            "end_time": "17:15",
            "duration": "30",
            "total_distance_yards": "736",
            "location": "Minnetonka",
            "comments": "",
            "freestyle_distance": "500",
            "breaststroke_distance": "100",
            "backstroke_distance": "0",
            "butterfly_distance": "0",
        },
        follow_redirects=True,
    )

    assert b"Stroke total does not equal total distance" in response.data
    with app.app_context():
        assert Workout.query.count() == 0
        assert UploadSession.query.count() == 1


def test_review_shows_duplicate_warning(app, client):
    login(client)

    with app.app_context():
        create_workout()
        session = UploadSession(
            image_filename="fake.png",
            extracted_payload={
                "workout_date": "2026-03-24",
                "start_time": "16:45",
                "end_time": "17:15",
                "duration": 30,
                "total_distance_yards": 736,
                "location": "Minnetonka",
                "comments": "",
                "freestyle_distance": 598,
                "breaststroke_distance": 138,
                "backstroke_distance": 0,
                "butterfly_distance": 0,
                "raw_strokes": [],
                "unknown_strokes": [],
                "ocr_text": "",
            },
        )
        db.session.add(session)
        db.session.commit()
        upload_id = session.id

    response = client.get(f"/review/{upload_id}")

    assert b"Possible duplicate" in response.data


def test_review_save_deletes_uploaded_file_after_success(app, client):
    login(client)

    upload_path = Path(app.root_path).parent / "uploads" / "delete-me.png"
    upload_path.write_bytes(b"fake image")

    with app.app_context():
        session = UploadSession(
            image_filename="delete-me.png",
            extracted_payload={
                "workout_date": "2026-03-24",
                "start_time": "16:45",
                "end_time": "17:15",
                "duration": 30,
                "total_distance_yards": 736,
                "location": "Minnetonka",
                "comments": "",
                "freestyle_distance": 598,
                "breaststroke_distance": 138,
                "backstroke_distance": 0,
                "butterfly_distance": 0,
                "raw_strokes": [],
                "unknown_strokes": [],
                "ocr_text": "",
            },
        )
        db.session.add(session)
        db.session.commit()
        upload_id = session.id

    response = client.post(
        f"/review/{upload_id}",
        data={
            "upload_id": str(upload_id),
            "workout_date": "2026-03-24",
            "start_time": "16:45",
            "end_time": "17:15",
            "duration": "30",
            "total_distance_yards": "736",
            "location": "Minnetonka",
            "comments": "",
            "freestyle_distance": "598",
            "breaststroke_distance": "138",
            "backstroke_distance": "0",
            "butterfly_distance": "0",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert not upload_path.exists()


def test_manage_workouts_requires_login(client):
    response = client.get("/workouts")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_manage_workouts_shows_recent_workouts_by_default(app, client):
    login(client)
    today = date.today()

    with app.app_context():
        for index in range(12):
            create_workout(
                start_date_time=datetime.combine(today - timedelta(days=index), datetime.min.time()).replace(hour=7, minute=15),
                location=f"Pool {index}",
                freestyle_distance=736,
                breaststroke_distance=None,
            )

    response = client.get("/workouts")

    assert b"Manage Workouts" in response.data
    tenth_day = (today - timedelta(days=9)).strftime("%Y-%m-%d 07:15").encode()
    eleventh_day = (today - timedelta(days=10)).strftime("%Y-%m-%d 07:15").encode()
    newest_day = today.strftime("%Y-%m-%d 07:15").encode()
    assert newest_day in response.data
    assert tenth_day in response.data
    assert eleventh_day not in response.data


def test_manage_workouts_filters_by_last_x_days_and_limit(app, client):
    login(client)
    today = date.today()

    with app.app_context():
        create_workout(
            start_date_time=datetime.combine(today - timedelta(days=1), datetime.min.time()).replace(hour=16, minute=45),
            location="Minnetonka",
        )
        create_workout(
            start_date_time=datetime.combine(today - timedelta(days=3), datetime.min.time()).replace(hour=18, minute=0),
            location="St. Louis Park",
            freestyle_distance=736,
            breaststroke_distance=None,
        )
        create_workout(
            start_date_time=datetime.combine(today - timedelta(days=12), datetime.min.time()).replace(hour=7, minute=15),
            location="YWCA",
            freestyle_distance=736,
            breaststroke_distance=None,
        )

    response = client.get("/workouts?days=7&limit=1")

    newest_in_window = (today - timedelta(days=1)).strftime("%Y-%m-%d 16:45").encode()
    older_in_window = (today - timedelta(days=3)).strftime("%Y-%m-%d 18:00").encode()
    outside_window = (today - timedelta(days=12)).strftime("%Y-%m-%d 07:15").encode()
    assert newest_in_window in response.data
    assert older_in_window not in response.data
    assert outside_window not in response.data
    assert b"YWCA" not in response.data


def test_edit_workout_updates_existing_record(app, client):
    login(client)

    with app.app_context():
        workout = create_workout(comments="Before")
        workout_id = workout.id

    response = client.post(
        f"/workouts/{workout_id}/edit",
        data={
            "workout_date": "2026-03-24",
            "start_time": "17:00",
            "end_time": "17:30",
            "duration": "30",
            "total_distance_yards": "800",
            "location": "Minnetonka Community Center",
            "comments": "After",
            "freestyle_distance": "600",
            "breaststroke_distance": "100",
            "backstroke_distance": "100",
            "butterfly_distance": "0",
        },
        follow_redirects=True,
    )

    assert b"Workout updated." in response.data
    with app.app_context():
        workout = db.session.get(Workout, workout_id)
        assert workout.start_date_time == datetime(2026, 3, 24, 17, 0)
        assert workout.location == "Minnetonka Community Center"
        assert workout.total_distance_yards == 800
        assert workout.comments == "After"
        assert workout.backstroke_distance == 100


def test_edit_workout_blocks_mismatched_strokes_without_override(app, client):
    login(client)

    with app.app_context():
        workout = create_workout()
        workout_id = workout.id

    response = client.post(
        f"/workouts/{workout_id}/edit",
        data={
            "workout_date": "2026-03-24",
            "start_time": "16:45",
            "end_time": "17:15",
            "duration": "30",
            "total_distance_yards": "736",
            "location": "Minnetonka",
            "comments": "",
            "freestyle_distance": "500",
            "breaststroke_distance": "100",
            "backstroke_distance": "0",
            "butterfly_distance": "0",
        },
        follow_redirects=True,
    )

    assert b"Stroke total does not equal total distance" in response.data
    with app.app_context():
        workout = db.session.get(Workout, workout_id)
        assert workout.total_distance_yards == 736
        assert workout.freestyle_distance == 598


def test_edit_workout_duplicate_warning_excludes_self_and_detects_other_rows(app, client):
    login(client)

    with app.app_context():
        primary = create_workout()
        primary_id = primary.id

    self_response = client.get(f"/workouts/{primary_id}/edit")
    assert b"Possible duplicate" not in self_response.data

    with app.app_context():
        create_workout(
            start_date_time=datetime(2026, 3, 24, 16, 45),
            location="Minnetonka",
            freestyle_distance=736,
            breaststroke_distance=None,
        )

    duplicate_response = client.get(f"/workouts/{primary_id}/edit")
    assert b"Possible duplicate" in duplicate_response.data


def test_delete_workout_confirmation_and_submit(app, client):
    login(client)

    with app.app_context():
        workout = create_workout(comments="Delete me")
        workout_id = workout.id

    confirm_response = client.get(f"/workouts/{workout_id}/delete")
    assert b"Delete Workout" in confirm_response.data
    assert b"Delete me" in confirm_response.data

    delete_response = client.post(
        f"/workouts/{workout_id}/delete",
        data={},
        follow_redirects=True,
    )

    assert b"Workout deleted." in delete_response.data
    with app.app_context():
        assert db.session.get(Workout, workout_id) is None


def test_manage_and_delete_missing_workout_returns_404(app, client):
    login(client)

    edit_response = client.get("/workouts/999/edit")
    delete_response = client.get("/workouts/999/delete")

    assert edit_response.status_code == 404
    assert delete_response.status_code == 404
