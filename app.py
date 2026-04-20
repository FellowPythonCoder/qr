from flask import Flask, request, redirect, session, send_file
import sqlite3, os, uuid, qrcode

app = Flask(__name__)
app.secret_key = "snap2see-ultra-ui"

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
scans INTEGER DEFAULT 0
)
""")

conn.commit()

# ================= APP STYLE =================
STYLE = """
<style>
body{
    margin:0;
    font-family:Arial;
    background: radial-gradient(circle at top, #1a1f2e, #05070d);
    color:white;
}

/* smooth animations */
.fade{
    animation: fade 0.6s ease;
}

@keyframes fade{
    from{opacity:0; transform:translateY(10px);}
    to{opacity:1; transform:translateY(0);}
}

/* glass UI */
.card{
    background:rgba(255,255,255,0.06);
    backdrop-filter: blur(18px);
    padding:25px;
    border-radius:18px;
    width:340px;
    box-shadow:0 10px 40px rgba(0,0,0,0.5);
    text-align:center;
}

.center{
    display:flex;
    height:100vh;
    align-items:center;
    justify-content:center;
    flex-direction:column;
}

h1,h2{
    margin:5px;
}

p{
    opacity:0.7;
}

/* buttons */
.btn{
    width:100%;
    padding:12px;
    border:none;
    border-radius:12px;
    margin-top:10px;
    cursor:pointer;
    transition:0.2s;
    font-size:14px;
}

.btn:hover{
    transform:scale(1.03);
}

.primary{background:#4f7cff;color:white;}
.green{background:#00c853;color:black;}
.gray{background:#2a2f3a;color:white;}
.purple{background:#7c4dff;color:white;}

input{
    width:100%;
    padding:10px;
    margin:6px 0;
    border-radius:10px;
    border:none;
    background:#1c2230;
    color:white;
}

/* top bar */
.nav{
    padding:15px;
    background:rgba(0,0,0,0.4);
    display:flex;
    justify-content:space-between;
    backdrop-filter: blur(10px);
}
a{color:#7aa2ff;text-decoration:none;}
</style>
"""

# ================= SPLASH (APP STORE STYLE) =================
@app.route("/")
def splash():
    return STYLE + """
    <div class="center fade">
        <div class="card">
            <h1>Snap2See</h1>
            <p>Upload files. Generate QR codes. Track scans instantly.</p>

            <a href="/create">
                <button class="btn primary">Get Started</button>
            </a>

            <button class="btn gray">How it works</button>
            <button class="btn purple">Why Snap2See</button>
        </div>
    </div>
    """

# ================= CREATE ACCOUNT =================
@app.route("/create", methods=["GET","POST"])
def create():
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]

        c.execute("INSERT INTO users (username,password) VALUES (?,?)", (u,p))
        conn.commit()

        session["user_id"] = c.lastrowid
        return redirect("/payment")

    return STYLE + """
    <div class="center fade">
        <div class="card">
            <h2>Create Account</h2>

            <form method="post">
                <input name="username" placeholder="Username">
                <input name="password" type="password" placeholder="Password">

                <button class="btn green">Continue</button>
            </form>
        </div>
    </div>
    """

# ================= PAYMENT UI =================
@app.route("/payment")
def payment():
    return STYLE + """
    <div class="center fade">
        <div class="card">
            <h2>Upgrade Plan</h2>
            <p>$10 Pro Plan (Fake UI)</p>

            <a href="/activate">
                <button class="btn primary">Continue to Pro</button>
            </a>

            <a href="/dashboard">
                <button class="btn gray">Skip</button>
            </a>
        </div>
    </div>
    """

@app.route("/activate")
def activate():
    c.execute("UPDATE users SET is_pro=1 WHERE id=?", (session["user_id"],))
    conn.commit()
    return redirect("/dashboard")

# ================= DASHBOARD =================
@app.route("/dashboard")
def dashboard():
    return STYLE + """
    <div class="nav">
        <div>Snap2See</div>
        <div>
            <a href="/manage">Manage</a> |
            <a href="/analytics">Analytics</a>
        </div>
    </div>

    <div class="center fade">
        <div class="card">
            <h2>Create QR</h2>

            <form action="/upload" method="post" enctype="multipart/form-data">
                <input type="file" name="file">
                <button class="btn green">Generate QR</button>
            </form>
        </div>
    </div>
    """

# ================= UPLOAD + QR PREVIEW =================
@app.route("/upload", methods=["POST"])
def upload():
    file = request.files["file"]

    file_id = str(uuid.uuid4())
    filename = file_id + "_" + file.filename

    path = os.path.join(UPLOADS, filename)
    file.save(path)

    c.execute("INSERT INTO files (id,user_id,filename) VALUES (?,?,?)",
              (file_id, session["user_id"], filename))
    conn.commit()

    link = request.host_url.strip("/") + "/view/" + file_id

    qr = qrcode.make(link)
    qr.save(os.path.join(QRS, file_id + ".png"))

    # IMPORTANT: SHOW QR IMMEDIATELY
    return STYLE + f"""
    <div class="center fade">
        <div class="card">
            <h2>QR Generated</h2>

            <img src="/qr/{file_id}" width="200" style="margin:10px;border-radius:12px;">

            <p>Scan to open file instantly</p>

            <a href="/manage">
                <button class="btn primary">Go to Dashboard</button>
            </a>
        </div>
    </div>
    """

# ================= VIEW FILE =================
@app.route("/view/<id>")
def view(id):
    c.execute("SELECT filename FROM files WHERE id=?", (id,))
    file = c.fetchone()[0]

    c.execute("UPDATE files SET scans = scans + 1 WHERE id=?", (id,))
    conn.commit()

    return send_file(os.path.join(UPLOADS, file))

# ================= QR IMAGE =================
@app.route("/qr/<id>")
def qr(id):
    return send_file(os.path.join(QRS, id + ".png"))

# ================= MANAGE =================
@app.route("/manage")
def manage():
    c.execute("SELECT id, scans FROM files WHERE user_id=?", (session["user_id"],))
    rows = c.fetchall()

    html = STYLE + """
    <div class="nav">
        <div>Manage QR</div>
        <a href="/dashboard">Back</a>
    </div>

    <div class="center fade">
    """

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

    return STYLE + f"""
    <div class="center fade">
        <div class="card">
            <h2>Analytics</h2>
            <h1>{total}</h1>
            <p>Total QR scans</p>
        </div>
    </div>
    """

# ================= RUN =================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
