import os
import hashlib
import secrets
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote, urlparse

from flask import Flask, abort, jsonify, render_template, request, session, redirect, url_for
from werkzeug.utils import secure_filename


BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"
DATABASE = Path(os.environ.get("FOOD_JOURNAL_DB", INSTANCE_DIR / "food-journal.sqlite3"))
UPLOAD_DIR = BASE_DIR / "static" / "uploads"
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
MEAL_TIMES = {"Pagi", "Siang", "Malam"}

CREATOR_NAME = os.environ.get("MAKANIN_CREATOR_NAME", "Ayu Rahmawati")
CREATOR_SOCIALS = (
    (
        "Intagram",
        os.environ.get("MAKANIN_INSTAGRAM_URL", "https://www.instagram.com/.yuayurhmaa_/"),
    ),
    (
        "LinkedIn",
        os.environ.get(
            "MAKANIN_LINKEDIN_URL",
            "https://www.linkedin.com/in/ayu-rahmawati-1a3952432/?isSelfProfile=true",
        ),
    ),
    (
        "YouTube",
        os.environ.get("MAKANIN_YOUTUBE_URL", "https://www.youtube.com/@ayuayrahma"),
    ),
)

app = Flask(__name__)

app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET_KEY")
if not app.config["SECRET_KEY"]:
    raise RuntimeError("FLASK_SECRET_KEY belum dikonfigurasi.")

app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")

if not ADMIN_USERNAME or not ADMIN_PASSWORD:
    raise RuntimeError("ADMIN_USERNAME dan ADMIN_PASSWORD belum dikonfigurasi.")


def title_case(value):
    return " ".join(
        "-".join(part.capitalize() for part in word.split("-"))
        for word in value.strip().split()
    )


def normalize_location(value):
    normalized = title_case(value.replace(";", ","))
    parts = [part.strip(" ,") for part in normalized.split(",") if part.strip(" ,")]
    if parts and parts[-1].casefold() not in {"semarang", "kota semarang"}:
        parts.append("Semarang")
    return ", ".join(parts)


def parse_recommendation_form(form):
    name = title_case(form.get("name", ""))
    restaurant_name = title_case(form.get("restaurant_name", ""))
    location = normalize_location(form.get("location", ""))
    maps_url = form.get("maps_url", "").strip()
    uploader_name = title_case(form.get("uploader_name", ""))
    description = " ".join(form.get("description", "").split())
    meal_time = form.get("meal_time", "").strip()
    try:
        price = int(form.get("price", ""))
        rating = float(form.get("rating", ""))
    except ValueError:
        return None, "Harga dan rating harus berupa angka."

    if (
        not name or len(name) > 80 or not restaurant_name or len(restaurant_name) > 100
        or not location or len(location) > 100
        or len(uploader_name) > 80
    ):
        return None, "Nama menu, nama tempat, dan lokasi wajib diisi."
    if price < 0 or not 1 <= rating <= 5 or meal_time not in MEAL_TIMES:
        return None, "Periksa kembali harga, waktu makan, dan rating."
    if not description or len(description) > 600:
        return None, "Deskripsi wajib diisi (maksimal 600 karakter)."
    if maps_url:
        parsed_maps_url = urlparse(maps_url)
        maps_host = (parsed_maps_url.hostname or "").lower()
        if parsed_maps_url.scheme != "https" or not (
            maps_host == "maps.app.goo.gl"
            or maps_host == "google.com"
            or maps_host.endswith(".google.com")
        ):
            return None, "Gunakan tautan Google Maps yang diawali https://."

    return {
        "name": name,
        "restaurant_name": restaurant_name,
        "price": price,
        "location": location,
        "maps_url": maps_url,
        "meal_time": meal_time,
        "rating": rating,
        "description": description,
        "uploader_name": uploader_name,
        "show_uploader": int(
            form.get("show_uploader") == "1" and bool(uploader_name)
        ),
    }, None


def save_uploaded_images(uploads):
    files = [upload for upload in uploads if upload and upload.filename]
    if len(files) > 2:
        return None, "Maksimal dua foto untuk satu rekomendasi."

    validated = []
    for uploaded in files:
        extension = Path(secure_filename(uploaded.filename)).suffix.lower().lstrip(".")
        if extension not in ALLOWED_EXTENSIONS or not uploaded.mimetype.startswith("image/"):
            return None, "Gunakan gambar JPG, PNG, atau WebP."
        validated.append((uploaded, extension))

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    image_paths = []
    for uploaded, extension in validated:
        filename = f"{uuid.uuid4().hex}.{extension}"
        uploaded.save(UPLOAD_DIR / filename)
        image_paths.append(f"/static/uploads/{filename}")
    return image_paths, None


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
                restaurant_name TEXT NOT NULL DEFAULT '',
                maps_url TEXT NOT NULL DEFAULT '',
                price INTEGER NOT NULL,
                location TEXT NOT NULL,
                meal_time TEXT NOT NULL,
                rating REAL NOT NULL,
                description TEXT NOT NULL,
                image TEXT NOT NULL,
                image2 TEXT NOT NULL DEFAULT '',
                is_demo INTEGER NOT NULL DEFAULT 0,
                uploader_name TEXT NOT NULL DEFAULT '',
                show_uploader INTEGER NOT NULL DEFAULT 0,
                owner_token_hash TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(recommendations)")}
        if "is_demo" not in columns:
            connection.execute(
                "ALTER TABLE recommendations ADD COLUMN is_demo INTEGER NOT NULL DEFAULT 0"
            )

        if "uploader_name" not in columns:
            connection.execute(
                "ALTER TABLE recommendations ADD COLUMN uploader_name TEXT NOT NULL DEFAULT ''"
            )
        if "show_uploader" not in columns:
            connection.execute(
                "ALTER TABLE recommendations ADD COLUMN show_uploader INTEGER NOT NULL DEFAULT 0"
            )
        if "owner_token_hash" not in columns:
            connection.execute("ALTER TABLE recommendations ADD COLUMN owner_token_hash TEXT")
        if "restaurant_name" not in columns:
            connection.execute(
                "ALTER TABLE recommendations ADD COLUMN restaurant_name TEXT NOT NULL DEFAULT ''"
            )
            connection.execute(
                """UPDATE recommendations
                   SET name = 'Ketoprak', restaurant_name = 'Mas Kembar'
                   WHERE LOWER(TRIM(name)) = 'ketoprak mas kembar'"""
            )
        if "image2" not in columns:
            connection.execute(
                "ALTER TABLE recommendations ADD COLUMN image2 TEXT NOT NULL DEFAULT ''"
            )
        if "maps_url" not in columns:
            connection.execute(
                "ALTER TABLE recommendations ADD COLUMN maps_url TEXT NOT NULL DEFAULT ''"
            )
        connection.execute(
            """UPDATE recommendations SET
                   name = 'Soto Ayam',
                   restaurant_name = 'Soto Ayam Pak Min/Gereja (Soto Yesus)',
                   price = 10000,
                   location = 'Semarang Tengah, Semarang',
                   maps_url = 'https://maps.app.goo.gl/oupZ1MNhytrYSYJaA',
                   meal_time = 'Malam',
                   description = 'Cuma buka dari jam 00.00 sampai 03.00. Tempatnya ada di depan gereja, makanya disebut Soto Yesus. Makannya lesehan. Porsinya kecil, tapi rasanya enak banget dan bumbunya berasa; ayamnya juga lumayan banyak. Ada sate-satean dan kondimen lain yang bisa diambil sendiri dengan harga mulai Rp1.000-Rp5.000. Minumannya sudah disediakan dan di-pack, jadi tinggal ambil dari termos besar.',
                   image = '/static/uploads/soto_yesus.jpg',
                   image2 = '',
                   uploader_name = '',
                   show_uploader = 0
               WHERE LOWER(TRIM(name)) = 'ketoprak'
                 AND LOWER(TRIM(restaurant_name)) = 'mas kembar'
                 AND LOWER(TRIM(description)) = 'mantap porsi banyak'
                 AND price = 15000
                 AND LOWER(location) LIKE '%mulawarman%'"""
        )


@app.get("/")
def home():
    initialize_database()
    return render_template(
        "index.html",
        creator_name=CREATOR_NAME,
        creator_socials=CREATOR_SOCIALS,
    )


@app.get("/recommendations/<int:recommendation_id>")
def recommendation_detail(recommendation_id):
    initialize_database()
    with get_db() as connection:
        row = connection.execute(
            """SELECT id, name, restaurant_name, price, location, meal_time, rating, description,
                      image, image2, maps_url,
                      CASE WHEN show_uploader = 1 THEN uploader_name ELSE '' END AS uploader_name
               FROM recommendations
               WHERE id = ? AND is_demo = 0""",
            (recommendation_id,),
        ).fetchone()
    if row is None:
        abort(404)
    recommendation = dict(row)
    recommendation["location_display"] = normalize_location(recommendation["location"])
    recommendation["map_url"] = recommendation["maps_url"] or (
        "https://www.google.com/maps/search/?api=1&query="
        + quote(recommendation["location_display"])
    )
    return render_template("recommendation.html", recommendation=recommendation)


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

    query = """SELECT id, name, restaurant_name, price, location, meal_time, rating, description,
                      image, image2, maps_url,
                      CASE WHEN show_uploader = 1 THEN uploader_name ELSE '' END
                        AS uploader_name,
                      show_uploader, created_at
               FROM recommendations WHERE """ + " AND ".join(conditions)
    query += " ORDER BY rating DESC, created_at DESC"

    with get_db() as connection:
        rows = connection.execute(query, values).fetchall()
    return jsonify([dict(row) for row in rows])


@app.get("/api/locations")
def list_locations():
    initialize_database()
    with get_db() as connection:
        rows = connection.execute(
            """SELECT DISTINCT location FROM recommendations
               WHERE is_demo = 0 AND TRIM(location) != ''
               ORDER BY location COLLATE NOCASE"""
        ).fetchall()
    locations = sorted(
        {normalize_location(row["location"]) for row in rows},
        key=str.casefold,
    )
    return jsonify(locations)


@app.post("/api/recommendations")
def create_recommendation():
    initialize_database()
    values, error = parse_recommendation_form(request.form)
    if error:
        return jsonify(error=error), 400
    images, error = save_uploaded_images(request.files.getlist("images"))
    if error:
        return jsonify(error=error), 400
    images = images or []

    edit_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(edit_token.encode()).hexdigest()

    with get_db() as connection:
        cursor = connection.execute(
            """INSERT INTO recommendations
               (name, restaurant_name, price, location, maps_url, meal_time, rating, description,
                image, image2,
                uploader_name, show_uploader, owner_token_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                values["name"], values["restaurant_name"], values["price"],
                values["location"], values["maps_url"], values["meal_time"],
                values["rating"], values["description"],
                images[0] if images else "", images[1] if len(images) > 1 else "",
                values["uploader_name"], values["show_uploader"], token_hash,
            ),
        )
        row = connection.execute(
            """SELECT id, name, restaurant_name, price, location, maps_url, meal_time,
                      rating, description, image, image2, uploader_name, show_uploader, created_at
               FROM recommendations WHERE id = ?""",
            (cursor.lastrowid,),
        ).fetchone()
    result = dict(row)
    result["edit_token"] = edit_token
    return jsonify(result), 201


@app.put("/api/recommendations/<int:recommendation_id>")
def update_recommendation(recommendation_id):
    initialize_database()
    provided_token = request.headers.get("X-Edit-Token", "")
    with get_db() as connection:
        existing = connection.execute(
            """SELECT image, image2, maps_url, owner_token_hash FROM recommendations
               WHERE id = ? AND is_demo = 0""",
            (recommendation_id,),
        ).fetchone()
        if existing is None:
            return jsonify(error="Menu rekomendasi tidak ditemukan."), 404
        if not existing["owner_token_hash"] or not secrets.compare_digest(
            hashlib.sha256(provided_token.encode()).hexdigest(), existing["owner_token_hash"]
        ):
            return jsonify(error="Kamu hanya bisa mengubah rekomendasi milikmu."), 403

        values, error = parse_recommendation_form(request.form)
        if error:
            return jsonify(error=error), 400
        uploaded_images, error = save_uploaded_images(request.files.getlist("images"))
        if error:
            return jsonify(error=error), 400
        uploaded_images = uploaded_images or []
        image = uploaded_images[0] if uploaded_images else existing["image"]
        image2 = uploaded_images[1] if uploaded_images else existing["image2"]
        maps_url = values["maps_url"]
        connection.execute(
            """UPDATE recommendations SET name = ?, restaurant_name = ?, price = ?, location = ?,
                      maps_url = ?, meal_time = ?, rating = ?, description = ?, image = ?, image2 = ?,
                      uploader_name = ?, show_uploader = ? WHERE id = ?""",
            (
                values["name"], values["restaurant_name"], values["price"], values["location"],
                maps_url, values["meal_time"], values["rating"], values["description"],
                image, image2, values["uploader_name"], values["show_uploader"], recommendation_id,
            ),
        )
        row = connection.execute(
            """SELECT id, name, restaurant_name, price, location, maps_url, meal_time, rating,
                      description, image, image2, uploader_name, show_uploader, created_at
               FROM recommendations WHERE id = ?""",
            (recommendation_id,),
        ).fetchone()
    return jsonify(dict(row))


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")

        if (
            secrets.compare_digest(username, ADMIN_USERNAME)
            and secrets.compare_digest(password, ADMIN_PASSWORD)
        ):
            session["is_admin"] = True
            return redirect(url_for("admin_dashboard"))

        return render_template(
            "admin_login.html",
            error="Username atau password salah."
        ), 401

    return render_template("admin_login.html", error=None)


@app.get("/admin")
def admin_dashboard():
    if not session.get("is_admin"):
        return redirect(url_for("admin_login"))

    initialize_database()

    session.setdefault("csrf_token", secrets.token_urlsafe(32))

    with get_db() as connection:
        rows = connection.execute("""
            SELECT
                id, name, restaurant_name, price,
                location, is_demo, image, image2
            FROM recommendations
            ORDER BY created_at DESC
        """).fetchall()

    recommendations = [dict(row) for row in rows]

    return render_template(
        "admin_dashboard.html",
        recommendations=recommendations,
        csrf_token=session["csrf_token"]
    )


@app.post("/admin/delete/<int:recommendation_id>")
def admin_delete_recommendation(recommendation_id):
    if not session.get("is_admin"):
        return redirect(url_for("admin_login"))

    # Periksa token keamanan formulir
    provided_token = request.form.get("csrf_token", "")
    session_token = session.get("csrf_token", "")

    if (
        not session_token
        or not provided_token
        or not secrets.compare_digest(provided_token, session_token)
    ):
        abort(400, description="Token keamanan tidak valid. Muat ulang dashboard.")

    initialize_database()

    with get_db() as connection:
        item = connection.execute(
            """
            SELECT id, name, is_demo, image, image2
            FROM recommendations
            WHERE id = ?
            """,
            (recommendation_id,),
        ).fetchone()

        if item is None:
            abort(404, description="Rekomendasi tidak ditemukan.")

        # Data demo tidak boleh dihapus lewat dashboard admin
        if item["is_demo"]:
            abort(403, description="Data demo dilindungi.")



        # Hapus hanya entri jurnal yang terhubung
        # ke rekomendasi yang sedang dihapus
        connection.execute(
            """
            DELETE FROM journal
            WHERE recommendation_id = ?
            """,
            (recommendation_id,),
        )

        # Setelah jurnal terkait dihapus, hapus rekomendasi
        connection.execute(
            "DELETE FROM recommendations WHERE id = ?",
            (recommendation_id,),
        )



        image_paths = [item["image"], item["image2"]]

        connection.execute(
            "DELETE FROM recommendations WHERE id = ?",
            (recommendation_id,),
        )

        # Hapus foto hanya jika tidak dipakai rekomendasi lain
        for image_path in image_paths:
            if not image_path or not image_path.startswith("/static/uploads/"):
                continue

            filename = Path(urlparse(image_path).path).name
            if not filename:
                continue

            image_file = (UPLOAD_DIR / filename).resolve()

            if image_file.parent != UPLOAD_DIR.resolve():
                continue

            still_used = connection.execute(
                """
                SELECT 1 FROM recommendations
                WHERE image = ? OR image2 = ?
                LIMIT 1
                """,
                (image_path, image_path),
            ).fetchone()

            if not still_used and image_file.is_file():
                image_file.unlink()

    return redirect(url_for("admin_dashboard"))




if __name__ == "__main__":
    app.run(debug=True)