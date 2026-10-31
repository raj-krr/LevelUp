"""Unit and integration tests for LevelUp Flask application routes."""

import io
import json
import pytest
from app import app, ALLOWED_LANGUAGES, ALLOWED_GRADES, ALLOWED_SUBJECTS, _rate_store


@pytest.fixture(autouse=True)
def clear_rate_limits():
    """Clear in-memory rate limit store before and after each test."""
    _rate_store.clear()
    yield
    _rate_store.clear()


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_index_route(client):
    """GET / returns the HTML page with status 200."""
    response = client.get("/")
    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert "LevelUp" in html
    assert "Your kid&#39;s homework. Your language. Level up." in html or "Your kid's homework" in html
    # Check that language options are rendered
    for name, code in ALLOWED_LANGUAGES:
        assert name in html
    # Check grade options are rendered
    for grade in ALLOWED_GRADES:
        assert str(grade) in html


def test_healthz_route(client):
    """GET /healthz returns ok status and model name."""
    response = client.get("/healthz")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "ok"
    assert "model" in data


def test_explain_no_image(client):
    """POST /api/explain without image returns 400."""
    response = client.post("/api/explain", data={
        "language": "English",
        "grade": "5",
        "subject": "Math"
    })
    assert response.status_code == 400
    data = response.get_json()
    assert "error" in data


def test_explain_non_image_file(client):
    """POST /api/explain with non-image file returns 400."""
    data = {
        "image": (io.BytesIO(b"Hello text file"), "test.txt", "text/plain"),
        "language": "English",
        "grade": "5",
        "subject": "Math"
    }
    response = client.post(
        "/api/explain",
        data=data,
        content_type="multipart/form-data"
    )
    assert response.status_code == 400
    data = response.get_json()
    assert "photo" in data["error"].lower() or "image" in data["error"].lower()


def test_explain_empty_image(client):
    """POST /api/explain with 0 byte image returns 400."""
    data = {
        "image": (io.BytesIO(b""), "empty.jpg", "image/jpeg"),
        "language": "English",
        "grade": "5",
        "subject": "Math"
    }
    response = client.post(
        "/api/explain",
        data=data,
        content_type="multipart/form-data"
    )
    assert response.status_code == 400
    data = response.get_json()
    assert "empty" in data["error"].lower()


def test_explain_rate_limit(client):
    """Rapid requests exceed rate limit and trigger 429."""
    # Send 10 rapid bad requests to trigger rate limit
    responses = []
    for _ in range(12):
        resp = client.post("/api/explain", data={})
        responses.append(resp.status_code)
    assert 429 in responses


def test_check_work_no_image(client):
    """POST /api/check without image returns 400."""
    response = client.post("/api/check", data={
        "language": "English",
        "grade": "5",
        "subject": "Math"
    })
    assert response.status_code == 400
    data = response.get_json()
    assert "error" in data

