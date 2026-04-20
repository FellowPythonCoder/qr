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

# ================= SPLASH (ONBOARDING) =================
@app.route("/")
def splash():
    return """
    <html>
    <head>
    <style>
        body{
            margin:0;
            font-family:Arial;
            background:#0f0f10;
            color:white;
        }
        .container{
            height:100vh;
            overflow-y:scroll;
            scroll-snap-type:y mandatory;
        }
        .page{
            height:100vh;
            display:flex;
            align-items:center;
            justify-content:center;
            flex-direction:column;
            scroll-snap-align:start;
            padding:40px;
            text-align:center;
        }
        .title{font-size:40px;margin-bottom:10px;}
        .btn{
            padding:12px 20px;
            background:white;
            color:black;
            border-radius:10px;
            text-decoration:none;
            margin-top:20px;
        }
        .card{
            background:#1c1c1e;
            padding:20px;
            border-radius:15px;
            width:300px;
        }
        input{
            width:90%;
            padding:10px;
            margin:8px;
            border-radius:10px;
            border:none;
            background:#2c2c2e;
            color:white;
        }
    </style>
    </head>

    <body>
    <div class="container">

        <div class="page">
            <div class="title">Snap2See</div>
            <div>QR platform for files and tracking</div>
            <a class="btn" href="/login">Start</a>
        </div>

        <div class="page">
            <h2>What you can do</h2>
            <p>Create QR codes that open files instantly</p>
        </div>

        <div class="page">
            <h2>Manage everything</h2>
            <p>Track scans and update QR content anytime</p>
        </div>

    </div>
    </body>
    </html>
    """

# ================= LOGIN / CREATE =================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]

        c.execute("SELECT * FROM users WHERE username=? AND password=?", (u, p))
        user = c.fetchone()

        if not user:
            c.execute("INSERT INTO users (username,password) VALUES (?,?)", (u, p))
            conn.commit()
            user_id = c.lastrowid
        else:
            user_id = user[0]

        session["user_id"] = user_id
        return redirect("/dashboard")

    return """
    <html>
    <body style="margin:0;background:#0f0f10;color:white;font-family:Arial;
    display:flex;align-items:center;justify-content:center;height:100vh;">

    <div style="background:#1c1c1e;padding:30px;border-radius:15px;width:320px;">
        <h2>Create account</h2>

        <form method="post">
            <input name="username" placeholder="Username"><br>
            <input name="password" type="password" placeholder="Password"><br>
            <button style="width:100%;padding:10px;margin-top:10px;">Continue</button>
        </form>
    </div>

    </body>
    </html>
    """

# ================= DASHBOARD =================
@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect("/login")

    return """
    <html>
    <body style="margin:0;background:#0f0f10;color:white;font-family:Arial;">

    <div style="padding:20px;background:#1c1c1e;">
        <h2>Dashboard</h2>
        <a href="/analytics" style="color:#4da6ff;">Analytics</a> |
        <a href="/manage" style="color:#4da6ff;">Manage QR</a>
    </div>

    <div style="padding:20px;">
        <form action="/upload" method="post" enctype="multipart/form-data">
            <input type="file" name="file">
            <button>Create QR</button>
        </form>
    </div>

    </body>
    </html>
    """

# ================= UPLOAD =================
@app.route("/upload", methods=["POST"])
def upload():
    file = request.files["file"]

    file_id = str(uuid.uuid4())
    filename = file_id + "_" + file.filename

    path = os.path.join(UPLOADS, filename)
    file.save(path)

    c.execute("""
        INSERT INTO files (id,user_id,filename,created)
        VALUES (?,?,?,?)
    """, (file_id, session["user_id"], filename, datetime.now()))

    conn.commit()

    base = request.host_url.strip("/")
    link = f"{base}/view/{file_id}"

    img = qrcode.make(link)
    img.save(os.path.join(QRS, file_id + ".png"))

    return redirect("/manage")

# ================= VIEW =================
@app.route("/view/<id>")
def view(id):
    c.execute("SELECT filename FROM files WHERE id=?", (id,))
    data = c.fetchone()

    if not data:
        return "Not found"

    filename = data[0]

    c.execute("UPDATE files SET scans = scans + 1 WHERE id=?", (id,))
    conn.commit()

    return send_file(os.path.join(UPLOADS, filename))

# ================= MANAGE =================
@app.route("/manage")
def manage():
    c.execute("SELECT id, scans FROM files WHERE user_id=?", (session["user_id"],))
    rows = c.fetchall()

    html = "<h2>Manage QR Codes</h2>"

    for r in rows:
        html += f"""
        <div style="padding:10
