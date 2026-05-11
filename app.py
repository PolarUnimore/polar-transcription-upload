import os
import json
import re
from datetime import datetime
from pathlib import Path

import dropbox
from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

load_dotenv()

DROPBOX_APP_KEY = os.getenv("DROPBOX_APP_KEY")
DROPBOX_APP_SECRET = os.getenv("DROPBOX_APP_SECRET")
DROPBOX_REFRESH_TOKEN = os.getenv("DROPBOX_REFRESH_TOKEN")
DROPBOX_UPLOAD_FOLDER = os.getenv("DROPBOX_UPLOAD_FOLDER", "/input")
UPLOAD_PASSWORD = os.getenv("UPLOAD_PASSWORD", "change-password")
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "2048"))

ALLOWED_EXTENSIONS = {
    "mp4", "mov", "mkv", "avi", "webm", "mpeg", "mpg",
    "mp3", "wav", "m4a", "aac", "flac"
}

ALLOWED_LANGUAGES = {"Italian", "French", "Spanish", "German", "Other"}

ALLOWED_CATEGORIES = {
    "Election_Speeches",
    "Parliamentary_Speeches",
    "Party_Conventions",
    "PressConferences_Interviews",
    "Talkshows",
    "Other"
}

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "change-this-secret-key")
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def clean_part(value):
    value = value.strip()
    value = re.sub(r"\s+", "_", value)
    value = re.sub(r"[^A-Za-z0-9_\-]", "", value)
    return value[:80] or "untitled"


def unique_dropbox_path(dbx, folder, filename):
    folder = folder.rstrip("/")
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    candidate = f"{folder}/{filename}"
    counter = 1

    while True:
        try:
            dbx.files_get_metadata(candidate)
            candidate = f"{folder}/{stem}_{counter}{suffix}"
            counter += 1
        except dropbox.exceptions.ApiError:
            return candidate


def login_required():
    return session.get("authenticated") is True

@app.route("/", methods=["GET"])
def index():
    if not login_required():
        return redirect(url_for("login"))
    return render_template("index.html", max_upload_mb=MAX_UPLOAD_MB)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        password = request.form.get("password", "")
        if password == UPLOAD_PASSWORD:
            session["authenticated"] = True
            return redirect(url_for("index"))
        flash("Incorrect password.", "error")
    return render_template("login.html")


@app.route("/logout", methods=["GET"])
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/upload", methods=["POST"])
def upload():
    if not login_required():
        return redirect(url_for("login"))

    if not DROPBOX_APP_KEY or not DROPBOX_APP_SECRET or not DROPBOX_REFRESH_TOKEN:
        flash("Configuration error: Dropbox refresh token configuration is incomplete.", "error")
        return redirect(url_for("index"))

    first_name = request.form.get("first_name", "").strip()
    last_name = request.form.get("last_name", "").strip()
    email = request.form.get("email", "").strip()

    title = request.form.get("title", "").strip()
    speakers = request.form.get("speakers", "").strip()
    political_party = request.form.get("political_party", "").strip()
    language = request.form.get("language", "").strip()
    category = request.form.get("category", "").strip()
    speech_date = request.form.get("speech_date", "").strip()
    source_url = request.form.get("source_url", "").strip()
    last_access_date = request.form.get("last_access_date", "").strip()
    notes = request.form.get("notes", "").strip()

    file = request.files.get("file")

    required_values = [
        first_name, last_name, email,
        title, speakers, political_party, language, category, source_url
    ]

    if not all(required_values):
        flash("Please complete all required fields.", "error")
        return redirect(url_for("index"))

    if language not in ALLOWED_LANGUAGES:
        flash("Please select a valid language.", "error")
        return redirect(url_for("index"))

    if category not in ALLOWED_CATEGORIES:
        flash("Please select a valid category.", "error")
        return redirect(url_for("index"))

    if not file or file.filename == "":
        flash("Please select a file.", "error")
        return redirect(url_for("index"))

    if not allowed_file(file.filename):
        flash("File format not allowed.", "error")
        return redirect(url_for("index"))

    original_filename = secure_filename(file.filename)
    extension = original_filename.rsplit(".", 1)[1].lower()

    safe_title = clean_part(title)

    base_filename = safe_title
    final_filename = f"{safe_title}.{extension}"
    metadata_filename = f"{safe_title}.json"

    metadata = {
        "status": "uploaded",
        "notification_sent": False,
        "uploader": {
            "first_name": first_name,
            "last_name": last_name,
            "email": email
        },
        "document": {
            "title": title,
            "speakers": speakers,
            "political_party": political_party,
            "language": language,
            "category": category,
            "speech_date": speech_date,
            "source_url": source_url,
            "last_access_date": last_access_date,
            "notes": notes
        },
        "file": {
            "original_filename": file.filename,
            "saved_filename": final_filename,
            "base_filename": base_filename,
            "uploaded_at": datetime.now().isoformat(timespec="seconds"),
            "expected_transcript_files": [
                f"{base_filename}_text.txt",
                f"{base_filename}_timestampText.txt",
                f"{base_filename}_segments.txt"
            ]
        }
    }

    try:
        dbx = dropbox.Dropbox(
    oauth2_refresh_token=DROPBOX_REFRESH_TOKEN,
    app_key=DROPBOX_APP_KEY,
    app_secret=DROPBOX_APP_SECRET,
)

        media_path = unique_dropbox_path(dbx, DROPBOX_UPLOAD_FOLDER, final_filename)
        metadata_path = unique_dropbox_path(dbx, DROPBOX_UPLOAD_FOLDER, metadata_filename)

        file.stream.seek(0)
        dbx.files_upload(
            file.stream.read(),
            media_path,
            mode=dropbox.files.WriteMode("add"),
            mute=True,
        )

        metadata["dropbox"] = {
            "media_path": media_path,
            "metadata_path": metadata_path
        }

        dbx.files_upload(
            json.dumps(metadata, ensure_ascii=False, indent=2).encode("utf-8"),
            metadata_path,
            mode=dropbox.files.WriteMode("add"),
            mute=True,
        )

        return render_template("success.html", email=email)

    except Exception as e:
        flash(f"Dropbox upload error: {e}", "error")
        return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050)
