from flask import Flask, request, redirect, session, send_file
import sqlite3, os, uuid, qrcode
from datetime import datetime

app = Flask(__name__)
app.secret_key = "snap2see-key"

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

# ================= UI STYLE =================
STYLE = """
<style>
body{
    margin:0;
    font-family:Arial;
    background:#0b0f19;
    color:white;
}

.screen{
    height:100vh;
    display:flex;
    align-items:center;
    justify-content:center;
    flex-direction:column;
}

.card{
    background:#141b2d;
    padding:20px;
    border-radius:16px;
    width:320px;
}

input{
    width:100%;
    padding:10px;
    margin:6px 0;
    border-radius:10px;
    border:none;
    background:#1f2a44;
    color:white;
}

button{
    width:100%;
    padding:10px;
    border:none;
    border-radius:10px;
    background:#4f7cff;
    color:white;
    cursor:pointer;
}

.nav{
    padding:15px;
    background:#10182a;
    display:flex;
    justify-content:space-between;
}
a{color:#7aa2ff;text-decoration:none;}
</style>
"""

# ================= SPLASH =================
@app.route("/")
def splash():
    return STYLE + """
    <div class="screen">
        <h1>Snap2See</h1>
        <p>Upload → QR → Share instantly</p>
        <a href="/login">Start</a>
    </div>
    """

# ================= LOGIN =================
@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]

        c.execute("SELECT * FROM users WHERE username=? AND password=?", (u,p))
        user = c.fetchone()

        if not user:
            c.execute("INSERT INTO users (username,password) VALUES (?,?)", (u,p))
            conn.commit()
            user_id = c.lastrowid
        else:
            user_id = user[0]

        session["user_id"] = user_id
        return redirect("/dashboard")

    return STYLE + """
    <div class="screen">
        <div class="card">
            <h2>Login</h2>
            <form method="post">
                <input name="username" placeholder="username">
                <input name="password" type="password" placeholder="password">
                <button>Continue</button>
            </form>
        </div>
    </div>
    """

# ================= DASHBOARD =================
@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect("/login")

    return STYLE + """
    <div class="nav">
        <div>Snap2See</div>
        <div>
            <a href="/analytics">Analytics</a> |
            <a href="/manage">Manage</a>
        </div>
    </div>

    <div class="screen">
        <div class="card">
            <h3>Create QR</h3>
            <form action="/upload" method="post" enctype="multipart/form-data">
                <input type="file" name="file">
                <button>Generate</button>
            </form>
        </div>
    </div>
    """

# ================= UPLOAD + SHOW QR =================
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

    qr_img = qrcode.make(link)
    qr_path = os.path.join(QRS, file_id + ".png")
    qr_img.save(qr_path)

    # IMPORTANT: show QR immediately
    return STYLE + f"""
    <div class="screen">
        <div class="card">
            <h2>QR Created</h2>
            <img src="/qr/{file_id}" width="200">
            <p>Scan to open file</p>
            <a href="/manage">Go to Manager</a>
        </div>
    </div>
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

    c.execute("UPDATE files SET scans = scans + 1 WHERE id=?", (id,))
    conn.commit()

    return send_file(os.path.join(UPLOADS, data[0]))

# ================= MANAGE =================
@app.route("/manage")
def manage():
    c.execute("SELECT id, scans FROM files WHERE user_id=?", (session["user_id"],))
    rows = c.fetchall()

    html = STYLE + "<div class='nav'><div>Manager</div><a href='/dashboard'>Back</a></div>"
    html += "<div class='screen'>"

    for r in rows:
        html += f"""
        <div class="card">
            <p>{r[0]}</p>
            <p>Scans: {r[1]}</p>
            <a href="/view/{r[0]}">Open</a>
        </div>
        """

    html += "</div>"
    return html

# ================= ANALYTICS =================
@app.route("/analytics")
def analytics():
    c.execute("SELECT scans FROM files WHERE user_id=?", (session["user_id"],))
    rows = c.fetchall()

    total = sum(r[0] for r in rows)

    html = STYLE + "<div class='nav'><div>Analytics</div><a href='/dashboard'>Back</a></div>"
    html += f"""
    <div class="screen">
        <div class="card">
            <h2>Total Scans</h2>
            <h1>{total}</h1>
        </div>
    </div>
    """

    return html

# ================= RUN =================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
