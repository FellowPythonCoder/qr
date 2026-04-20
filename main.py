from flask import Flask, request, redirect, session, send_file
import sqlite3, os, uuid, qrcode
from datetime import datetime

app = Flask(__name__)
app.secret_key = "snap2see-secret"

UPLOADS = "uploads"
QRS = "qrs"

os.makedirs(UPLOADS, exist_ok=True)
os.makedirs(QRS, exist_ok=True)

# ================= DATABASE =================
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

# ================= SPLASH =================
@app.route("/")
def splash():
    return """
    <html>
    <body style="margin:0;background:linear-gradient(45deg,#833ab4,#fd1d1d,#fcb045);
    height:100vh;display:flex;align-items:center;justify-content:center;font-family:Arial;">
        <div style="text-align:center;color:white;">
            <h1 style="font-size:50px;">Snap2See</h1>
            <p>Smart QR SaaS Platform</p>
            <a href="/login" style="padding:10px 20px;background:white;color:black;border-radius:10px;text-decoration:none;">Enter</a>
        </div>
    </body>
    </html>
    """

# ================= LOGIN =================
@app.route("/login", methods=["GET", "POST"])
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
    <html>
    <body style="background:#111;color:white;font-family:Arial;text-align:center;">
        <h2>Login</h2>
        <form method="post">
            <input name="username" placeholder="username"><br><br>
            <input name="password" type="password" placeholder="password"><br><br>
            <button>Login</button>
        </form>
    </body>
    </html>
    """

# ================= DASHBOARD =================
@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect("/login")

    c.execute("SELECT is_pro FROM users WHERE id=?", (session["user_id"],))
    pro = c.fetchone()[0]

    return f"""
    <html>
    <body style="font-family:Arial;background:#0f0f10;color:white;">
        <div style="padding:20px;background:#1c1c1e;">
            <h2>Snap2See Dashboard</h2>
            <a href="/upgrade" style="color:#ffcc00;">{"PRO USER" if pro else "Upgrade Pro ($10 fake)"}</a>
        </div>

        <div style="padding:20px;">
            <form action="/upload" method="post" enctype="multipart/form-data">
                <input type="file" name="file">
                <button>Create QR</button>
            </form>

            <br>
            <a href="/manage">Manage QR Codes</a>
        </div>
    </body>
    </html>
    """

# ================= UPGRADE =================
@app.route("/upgrade")
def upgrade():
    c.execute("UPDATE users SET is_pro=1 WHERE id=?", (session["user_id"],))
    conn.commit()
    return redirect("/dashboard")

# ================= UPLOAD + QR =================
@app.route("/upload", methods=["POST"])
def upload():
    file = request.files["file"]

    file_id = str(uuid.uuid4())
    filename = file_id + "_" + file.filename

    path = os.path.join(UPLOADS, filename)
    file.save(path)

    c.execute("""
        INSERT INTO files (id, user_id, filename, created)
        VALUES (?,?,?,?)
    """, (file_id, session["user_id"], filename, datetime.now()))

    conn.commit()

    base = request.host_url.strip("/")
    link = f"{base}/view/{file_id}"

    img = qrcode.make(link)
    qr_path = os.path.join(QRS, file_id + ".png")
    img.save(qr_path)

    return f"""
    <h2>QR Created</h2>
    <img src="/qr/{file_id}" width="200">
    <p>{link}</p>
    <a href="/dashboard">Back</a>
    """

# ================= QR IMAGE =================
@app.route("/qr/<id>")
def qr(id):
    return send_file(os.path.join(QRS, id + ".png"))

# ================= VIEW FILE =================
@app.route("/view/<id>")
def view(id):
    c.execute("SELECT filename FROM files WHERE id=?", (id,))
    data = c.fetchone()

    if not data:
        return "Not found"

    filename = data[0]

    c.execute("UPDATE files SET scans = scans + 1 WHERE id=?", (id,))
    conn.commit()

    file_path = os.path.join(UPLOADS, filename)

    return send_file(file_path)

# ================= MANAGE QR =================
@app.route("/manage")
def manage():
    c.execute("SELECT id, filename, scans FROM files WHERE user_id=?", (session["user_id"],))
    rows = c.fetchall()

    html = "<h2>My QR Codes</h2>"

    for r in rows:
        html += f"""
        <div style="padding:10px;border:1px solid #333;margin:10px;">
            <p>ID: {r[0]}</p>
            <p>Scans: {r[2]}</p>
            <a href="/view/{r[0]}">Open</a> |
            <a href="/edit/{r[0]}">Change File</a>
        </div>
        """

    return html

# ================= EDIT QR (DYNAMIC) =================
@app.route("/edit/<id>", methods=["GET", "POST"])
def edit(id):
    if request.method == "POST":
        file = request.files["file"]

        c.execute("SELECT filename FROM files WHERE id=?", (id,))
        old = c.fetchone()[0]

        path = os.path.join(UPLOADS, old)
        file.save(path)

        return redirect("/manage")

    return """
    <h2>Replace File for QR</h2>
    <form method="post" enctype="multipart/form-data">
        <input type="file" name="file">
        <button>Update</button>
    </form>
    """

# ================= RUN =================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="https://qr-0i2j.onrender.com", port=port)