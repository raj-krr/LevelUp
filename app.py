"""LevelUp — Flask application.

Routes, input validation, rate limiting, and request handling.
Images are processed in memory only — never written to disk or logged.
"""

import logging
import os
import time
from collections import defaultdict

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from flask import Flask, render_template, request, jsonify

import ai

# ---------------------------------------------------------------------------
# Logging — never log content, only operational data
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------
app = Flask(__name__)

# Maximum upload size: 5 MB
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
ALLOWED_LANGUAGES = [
    ("English", "en-IN"),
    ("हिन्दी", "hi-IN"),
    ("தமிழ்", "ta-IN"),
    ("తెలుగు", "te-IN"),
    ("বাংলা", "bn-IN"),
    ("मराठी", "mr-IN"),
]
LANGUAGE_NAMES = {name for name, _ in ALLOWED_LANGUAGES}

ALLOWED_GRADES = list(range(3, 9))  # 3 to 8

ALLOWED_SUBJECTS = ["Math", "Science", "English", "Social Studies", "Not sure"]
SUBJECT_SET = {s.lower() for s in ALLOWED_SUBJECTS}

RATE_LIMIT_PER_MIN = int(os.environ.get("RATE_LIMIT_PER_MIN", "8"))

# Log startup configuration
MAIN_MODEL = os.environ.get("GEMMA_MODEL", "gemma-4-26b-a4b-it")
VERIFY_MODEL = os.environ.get("GEMMA_VERIFY_MODEL", "gemma-4-31b-it")
logger.info("LevelUp starting — main_model=%s verify_model=%s rate_limit=%d/min",
            MAIN_MODEL, VERIFY_MODEL, RATE_LIMIT_PER_MIN)

# ---------------------------------------------------------------------------
# In-memory rate limiter (per-process, resets on restart)
# ---------------------------------------------------------------------------
_rate_store: dict[str, list[float]] = defaultdict(list)


def _check_rate_limit(ip: str) -> bool:
    """Return True if the request is allowed, False if rate-limited."""
    now = time.time()
    window = now - 60
    # Clean old timestamps
    _rate_store[ip] = [t for t in _rate_store[ip] if t > window]
    if len(_rate_store[ip]) >= RATE_LIMIT_PER_MIN:
        return False
    _rate_store[ip].append(now)
    return True


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    """Serve the single-page UI."""
    return render_template(
        "index.html",
        languages=ALLOWED_LANGUAGES,
        grades=ALLOWED_GRADES,
        subjects=ALLOWED_SUBJECTS,
    )


@app.route("/healthz")
def healthz():
    """Health check for DigitalOcean App Platform."""
    model = os.environ.get("GEMMA_MODEL", "gemma-4-26b-a4b-it")
    return jsonify({"status": "ok", "model": model})


@app.route("/api/explain", methods=["POST"])
def api_explain():
    """Process a homework photo and return an explanation.

    Accepts multipart/form-data with:
      - image (file, required)
      - language (string, default "English")
      - grade (int 3-8, default 5)
      - subject (string, default "Not sure")
    """
    # --- Rate limit ---
    client_ip = request.remote_addr or "unknown"
    if not _check_rate_limit(client_ip):
        return jsonify({
            "error": "Lots of people are learning right now! Please try again in a minute. 📚"
        }), 429

    # --- Validate image ---
    if "image" not in request.files:
        return jsonify({"error": "Please select a photo of the homework."}), 400

    image_file = request.files["image"]
    if not image_file.filename:
        return jsonify({"error": "Please select a photo of the homework."}), 400

    # Check content type
    mime_type = image_file.content_type or ""
    if not mime_type.startswith("image/"):
        return jsonify({
            "error": "That doesn't look like a photo. Please choose an image file."
        }), 400

    # Read image bytes (in memory only — never written to disk)
    image_bytes = image_file.read()
    if len(image_bytes) > 5 * 1024 * 1024:
        return jsonify({
            "error": "The photo is too large. Please take it from a bit further away or use gallery."
        }), 413

    if len(image_bytes) == 0:
        return jsonify({"error": "The photo appears empty. Please try again."}), 400

    # --- Validate form fields ---
    language = request.form.get("language", "English").strip()
    if language not in LANGUAGE_NAMES:
        language = "English"

    try:
        grade = int(request.form.get("grade", "5"))
    except (ValueError, TypeError):
        grade = 5
    if grade not in ALLOWED_GRADES:
        grade = max(3, min(8, grade))

    subject = request.form.get("subject", "Not sure").strip()
    if subject.lower() not in SUBJECT_SET:
        subject = "Not sure"

    # --- Check API key ---
    if not os.environ.get("GEMINI_API_KEY"):
        logger.error("GEMINI_API_KEY is not set")
        return jsonify({
            "error": "The service is not fully set up yet. Please try again later."
        }), 500

    # --- Call the explainer model ---
    try:
        result = ai.explain_homework(
            image_bytes=image_bytes,
            mime_type=mime_type,
            language=language,
            grade=grade,
            subject=subject,
        )
    except RuntimeError as e:
        if "rate_limited" in str(e):
            return jsonify({
                "error": "Lots of people are using this right now. Please try again in a minute. 📚"
            }), 429
        logger.info("explain_error=%s", type(e).__name__)
        return jsonify({
            "error": "Something went wrong while reading the homework. Please try again."
        }), 502

    # --- Early return for poor quality or non-homework ---
    if result.get("image_quality") == "poor":
        result["verified"] = None
        result["verify_note"] = ""
        return jsonify(result)

    if result.get("subject") == "not_homework":
        result["verified"] = None
        result["verify_note"] = ""
        return jsonify(result)

    # --- Verification pass ---
    if result.get("needs_verification", True):
        full_solution = result.get("hints", {}).get("full_solution", "")
        problem_summary = result.get("problem_summary", "")

        if full_solution and problem_summary:
            verify_result = ai.verify_solution(problem_summary, full_solution)

            if verify_result is None:
                result["verified"] = None
                result["verify_note"] = ""
            elif verify_result.get("agrees"):
                result["verified"] = True
                result["verify_note"] = ""
            else:
                result["verified"] = False
                result["confidence"] = "low"
                result["verify_note"] = verify_result.get("note", "")
        else:
            result["verified"] = None
            result["verify_note"] = ""
    else:
        # Model says verification not needed (e.g. essay questions)
        result["verified"] = None
        result["verify_note"] = ""

    return jsonify(result)


@app.route("/api/check", methods=["POST"])
def api_check():
    """Analyze a child's written work and provide constructive guidance.

    Accepts multipart/form-data with:
      - image (file, required)
      - language (string, default "English")
      - grade (int 3-8, default 5)
      - subject (string, default "Not sure")
      - problem_text (string, optional context)
    """
    # Rate limit check
    client_ip = request.remote_addr or "unknown"
    if not _check_rate_limit(client_ip):
        return jsonify({
            "error": "Lots of people are learning right now! Please try again in a minute. 📚"
        }), 429

    if "image" not in request.files:
        return jsonify({"error": "Please select a photo of your child's work."}), 400

    image_file = request.files["image"]
    if not image_file.filename:
        return jsonify({"error": "Please select a photo of your child's work."}), 400

    mime_type = image_file.content_type or ""
    if not mime_type.startswith("image/"):
        return jsonify({
            "error": "That doesn't look like a photo. Please choose an image file."
        }), 400

    image_bytes = image_file.read()
    if len(image_bytes) > 5 * 1024 * 1024:
        return jsonify({
            "error": "The photo is too large. Please resize it or take it from a bit further away."
        }), 413

    if len(image_bytes) == 0:
        return jsonify({"error": "The photo appears empty. Please try again."}), 400

    language = request.form.get("language", "English").strip()
    if language not in LANGUAGE_NAMES:
        language = "English"

    try:
        grade = int(request.form.get("grade", "5"))
    except (ValueError, TypeError):
        grade = 5
    if grade not in ALLOWED_GRADES:
        grade = max(3, min(8, grade))

    subject = request.form.get("subject", "Not sure").strip()
    if subject.lower() not in SUBJECT_SET:
        subject = "Not sure"

    problem_text = request.form.get("problem_text", "").strip()[:500]

    if not os.environ.get("GEMINI_API_KEY"):
        return jsonify({
            "error": "The service is not fully set up yet. Please try again later."
        }), 500

    try:
        check_result = ai.check_child_work(
            image_bytes=image_bytes,
            mime_type=mime_type,
            language=language,
            grade=grade,
            subject=subject,
            problem_text=problem_text,
        )
        return jsonify(check_result)
    except Exception as e:
        logger.info("check_error=%s", type(e).__name__)
        return jsonify({
            "error": "Could not review the work right now. Please try again."
        }), 502


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------
@app.errorhandler(413)
def too_large(e):
    """Handle file-too-large errors."""
    return jsonify({
        "error": "The photo is too large (max 5 MB). Please resize it or take it from further away."
    }), 413


@app.errorhandler(500)
def server_error(e):
    """Handle unexpected server errors."""
    logger.error("Unhandled 500: %s", type(e).__name__)
    return jsonify({
        "error": "Something unexpected happened. Please try again."
    }), 500


# ---------------------------------------------------------------------------
# Run locally
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    logger.info("Starting LevelUp dev server on port %d", port)
    app.run(host="0.0.0.0", port=port, debug=True)

