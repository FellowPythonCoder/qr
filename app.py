from flask import Flask, request, redirect, send_file, session
import sqlite3, os, uuid, qrcode
from datetime import datetime

app = Flask(__name__)
app.secret_key = "secret-key"

UPLOADS = "uploads"
QRS = "qrs"

os.makedirs(UPLOADS, exist_ok=True)
os.makedirs(QRS, exist_ok=True)

# ---------------- DATABASE ----------------
conn = sqlite3.connect("app.db", check_same_thread=False)
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT,
    password TEXT,
    is_pro INTEGER DEFAULT 0
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS files (
    id TEXT PRIMARY KEY,
    user_id INTEGER,
    filename TEXT,
    scans INTEGER DEFAULT 0,
    created TEXT
)
""")

conn.commit()

# ---------------- LOGIN ----------------
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]

        c.execute("SELECT * FROM users WHERE username=? AND password=?", (u, p))
        user = c.fetchone()

        if not user:
            c.execute("INSERT INTO users (username, password) VALUES (?,?)", (u, p))
            conn.commit()
            user_id = c.lastrowid
        else:
            user_id = user[0]

        session["user_id"] = user_id
        return redirect("/dashboard")

    return """
    <h2>Login</h2>
    <form method='post'>
        <input name='username' placeholder='username'>
        <input name='password' placeholder='password'>
        <button>Login</button>
    </form>
    """

# ---------------- DASHBOARD ----------------
@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect("/")

    return """
    <h1>Snap2See SaaS</h1>

    <form action="/upload" method="post" enctype="multipart/form-data">
        <input type="file" name="file">
        <button>Upload + Create QR</button>
    </form>

    <a href="/upgrade">Upgrade Pro ($10)</a>
    """

# ---------------- FAKE UPGRADE ----------------
@app.route("/upgrade")
def upgrade():
    c.execute("UPDATE users SET is_pro=1 WHERE id=?", (session["user_id"],))
    conn.commit()
    return redirect("/dashboard")

# ---------------- UPLOAD + QR ----------------
@app.route("/upload", methods=["POST"])
def upload():
    file = request.files["file"]

    file_id = str(uuid.uuid4())
    filename = file_id + "_" + file.filename

    path = os.path.join(UPLOADS, filename)
    file.save(path)

    # save DB
    c.execute("""
        INSERT INTO files (id, user_id, filename, created)
        VALUES (?,?,?,?)
    """, (file_id, session["user_id"], filename, datetime.now()))

    conn.commit()

    # PUBLIC URL (IMPORTANT FOR RENDER)
    base_url = request.host_url.strip("/")

    link = f"{base_url}/view/{file_id}"

    img = qrcode.make(link)
    qr_path = os.path.join(QRS, file_id + ".png")
    img.save(qr_path)

    return f"""
    <h2>QR Created</h2>
    <img src="/qr/{file_id}" width="200">
    <p>{link}</p>
    """

# ---------------- QR IMAGE ----------------
@app.route("/qr/<id>")
def qr(id):
    return send_file(os.path.join(QRS, id + ".png"))

# ---------------- VIEW FILE (SAAS PAGE) ----------------
@app.route("/view/<id>")
def view(id):
    c.execute("SELECT filename, scans FROM files WHERE id=?", (id,))
    data = c.fetchone()

    if not data:
        return "Not found"

    filename = data[0]

    # update scan count
    c.execute("UPDATE files SET scans = scans + 1 WHERE id=?", (id,))
    conn.commit()

    file_path = os.path.join(UPLOADS, filename)

    ext = filename.split(".")[-1].lower()

    if ext in ["png", "jpg", "jpeg", "gif"]:
        return f"""
        <html>
        <body style="background:#111;color:white;text-align:center;">
            <h2>Snap2See Viewer</h2>
            <img src="/file/{id}" style="max-width:90%;">
        </body>
        </html>
        """

    return send_file(file_path)

# ---------------- FILE SERVER ----------------
@app.route("/file/<id>")
def file(id):
    c.execute("SELECT filename FROM files WHERE id=?", (id,))
    filename = c.fetchone()[0]
    return send_file(os.path.join(UPLOADS, filename))

# ---------------- RUN ----------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
