from datetime import date, datetime

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
        db.session.add(
            Workout(
                start_date_time=datetime(2026, 3, 24, 16, 45),
                duration=30,
                total_distance_yards=736,
                location="Minnetonka",
                comments=None,
                freestyle_distance=598,
                breaststroke_distance=138,
                backstroke_distance=None,
                butterfly_distance=None,
            )
        )
        db.session.commit()

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
        db.session.add(
            Workout(
                start_date_time=datetime(2026, 3, 24, 16, 45),
                duration=30,
                total_distance_yards=736,
                location="Minnetonka",
                comments=None,
                freestyle_distance=598,
                breaststroke_distance=138,
                backstroke_distance=None,
                butterfly_distance=None,
            )
        )
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
