import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import date
from pathlib import Path

from flask import Flask, jsonify, render_template, request
from werkzeug.utils import secure_filename


BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"
DATABASE = Path(os.environ.get("FOOD_JOURNAL_DB", INSTANCE_DIR / "food-journal.sqlite3"))
UPLOAD_DIR = BASE_DIR / "static" / "uploads"
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
MEAL_TIMES = {"Pagi", "Siang", "Malam"}
LEGACY_DEMO_NAMES = (
    "Nasi Ayam Bu Wido",
    "Bubur Ayam Pak Brewok",
    "Soto Bangkong",
    "Nasi Kucing Angkringan Pak Gik",
    "Tahu Gimbal Pak H. Edy",
    "Pecel Mbok Sador",
)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

@contextmanager
def get_db():
    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize_database():
    with get_db() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS recommendations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                price INTEGER NOT NULL,
                location TEXT NOT NULL,
                meal_time TEXT NOT NULL,
                rating REAL NOT NULL,
                description TEXT NOT NULL,
                image TEXT NOT NULL,
                is_demo INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS journal (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recommendation_id INTEGER NOT NULL,
                eaten_on TEXT NOT NULL,
                logged_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (recommendation_id) REFERENCES recommendations(id)
            );
            """
        )
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(recommendations)")}
        if "is_demo" not in columns:
            connection.execute(
                "ALTER TABLE recommendations ADD COLUMN is_demo INTEGER NOT NULL DEFAULT 0"
            )
            placeholders = ", ".join("?" for _ in LEGACY_DEMO_NAMES)
            connection.execute(
                f"UPDATE recommendations SET is_demo = 1 WHERE name IN ({placeholders})",
                LEGACY_DEMO_NAMES,
            )


@app.get("/")
def home():
    initialize_database()
    return render_template("index.html")


@app.get("/api/recommendations")
def list_recommendations():
    initialize_database()
    conditions = ["is_demo = 0"]
    values = []
    budget = request.args.get("budget", type=int)
    location = request.args.get("location", "").strip()
    meal_time = request.args.get("meal_time", "").strip()

    if budget is not None and budget >= 0:
        conditions.append("price <= ?")
        values.append(budget)
    if location:
        conditions.append("location LIKE ?")
        values.append(f"%{location}%")
    if meal_time in MEAL_TIMES:
        conditions.append("meal_time = ?")
        values.append(meal_time)

    query = "SELECT * FROM recommendations WHERE " + " AND ".join(conditions)
    query += " ORDER BY rating DESC, created_at DESC"

    with get_db() as connection:
        rows = connection.execute(query, values).fetchall()
    return jsonify([dict(row) for row in rows])


@app.post("/api/recommendations")
def create_recommendation():
    initialize_database()
    name = request.form.get("name", "").strip()
    location = request.form.get("location", "").strip()
    description = request.form.get("description", "").strip()
    meal_time = request.form.get("meal_time", "").strip()
    try:
        price = int(request.form.get("price", ""))
        rating = float(request.form.get("rating", ""))
    except ValueError:
        return jsonify(error="Harga dan rating harus berupa angka."), 400

    if not name or len(name) > 80 or not location or len(location) > 100:
        return jsonify(error="Nama menu dan lokasi wajib diisi."), 400
    if price < 0 or not 1 <= rating <= 5 or meal_time not in MEAL_TIMES:
        return jsonify(error="Periksa kembali harga, waktu makan, dan rating."), 400
    if not description or len(description) > 600:
        return jsonify(error="Deskripsi wajib diisi (maksimal 600 karakter)."), 400

    image = "https://images.unsplash.com/photo-1547592180-85f173990554?auto=format&fit=crop&w=900&q=85"
    uploaded = request.files.get("image")
    if uploaded and uploaded.filename:
        extension = Path(secure_filename(uploaded.filename)).suffix.lower().lstrip(".")
        if extension not in ALLOWED_EXTENSIONS or not uploaded.mimetype.startswith("image/"):
            return jsonify(error="Gunakan gambar JPG, PNG, atau WebP."), 400
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"{uuid.uuid4().hex}.{extension}"
        uploaded.save(UPLOAD_DIR / filename)
        image = f"/static/uploads/{filename}"

    with get_db() as connection:
        cursor = connection.execute(
            """INSERT INTO recommendations
               (name, price, location, meal_time, rating, description, image)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (name, price, location, meal_time, rating, description, image),
        )
        row = connection.execute(
            "SELECT * FROM recommendations WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
    return jsonify(dict(row)), 201


@app.get("/api/journal")
def list_journal():
    initialize_database()
    with get_db() as connection:
        rows = connection.execute(
            """SELECT journal.id, journal.eaten_on, recommendations.name,
                      recommendations.price, recommendations.location,
                      recommendations.meal_time, recommendations.image
               FROM journal
               JOIN recommendations ON recommendations.id = journal.recommendation_id
               ORDER BY journal.eaten_on DESC, journal.logged_at DESC"""
        ).fetchall()
    return jsonify([dict(row) for row in rows])


@app.post("/api/journal")
def add_to_journal():
    initialize_database()
    payload = request.get_json(silent=True) or {}
    recommendation_id = payload.get("recommendation_id")
    eaten_on = payload.get("eaten_on") or date.today().isoformat()
    try:
        date.fromisoformat(eaten_on)
        recommendation_id = int(recommendation_id)
    except (TypeError, ValueError):
        return jsonify(error="Pilih menu dan tanggal yang valid."), 400

    with get_db() as connection:
        exists = connection.execute(
            "SELECT 1 FROM recommendations WHERE id = ?", (recommendation_id,)
        ).fetchone()
        if exists is None:
            return jsonify(error="Menu rekomendasi tidak ditemukan."), 404
        cursor = connection.execute(
            "INSERT INTO journal (recommendation_id, eaten_on) VALUES (?, ?)",
            (recommendation_id, eaten_on),
        )
        row = connection.execute(
            """SELECT journal.id, journal.eaten_on, recommendations.name,
                      recommendations.price, recommendations.location,
                      recommendations.meal_time, recommendations.image
               FROM journal JOIN recommendations
                 ON recommendations.id = journal.recommendation_id
               WHERE journal.id = ?""",
            (cursor.lastrowid,),
        ).fetchone()
    return jsonify(dict(row)), 201


if __name__ == "__main__":
    app.run(debug=True)