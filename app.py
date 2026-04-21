from flask import Flask, request, redirect, session, send_file
import sqlite3, os, uuid, qrcode
from datetime import datetime

app = Flask(__name__)
app.secret_key = "snap2see-secret"

UPLOADS = "uploads"
QRS = "qrs"

os.makedirs(UPLOADS, exist_ok=True)
os.makedirs(QRS, exist_ok=True)

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

# ── SHARED STYLES ──────────────────────────────────────────────────────────────
BASE_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }

:root {
    --bg: #000;
    --bg-1: #0a0a0a;
    --bg-2: #111;
    --bg-3: #1a1a1a;
    --glass: rgba(255,255,255,0.04);
    --glass-border: rgba(255,255,255,0.1);
    --glass-hover: rgba(255,255,255,0.07);
    --text: #f5f5f7;
    --text-2: #a1a1a6;
    --text-3: #6e6e73;
    --accent: #2997ff;
    --accent-dark: #0077ed;
    --accent-glow: rgba(41,151,255,0.3);
    --gold: #ffd60a;
    --gold-glow: rgba(255,214,10,0.25);
    --red: #ff453a;
    --green: #30d158;
    --radius: 14px;
    --radius-lg: 20px;
    --radius-xl: 28px;
}

html, body {
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", "Helvetica Neue", sans-serif;
    min-height: 100vh;
    -webkit-font-smoothing: antialiased;
}

a { color: inherit; text-decoration: none; }

.glass {
    background: var(--glass);
    border: 1px solid var(--glass-border);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
}

input[type=text], input[type=password], input[type=file] {
    width: 100%;
    padding: 14px 18px;
    background: var(--glass);
    border: 1px solid var(--glass-border);
    border-radius: var(--radius);
    color: var(--text);
    font-size: 15px;
    font-family: inherit;
    outline: none;
    transition: border-color .2s, box-shadow .2s;
}

input:focus {
    border-color: var(--accent);
    box-shadow: 0 0 0 3px var(--accent-glow);
}

input::placeholder { color: var(--text-3); }

input[type=file] {
    cursor: pointer;
    padding: 20px;
    border-style: dashed;
    text-align: center;
}

input[type=file]::-webkit-file-upload-button {
    background: var(--accent);
    color: #fff;
    border: none;
    padding: 8px 16px;
    border-radius: 8px;
    font-size: 13px;
    cursor: pointer;
    margin-right: 12px;
}

.btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    padding: 13px 24px;
    border-radius: var(--radius);
    font-size: 15px;
    font-weight: 500;
    cursor: pointer;
    border: none;
    transition: all .2s cubic-bezier(.25,.46,.45,.94);
    font-family: inherit;
    letter-spacing: -0.01em;
}

.btn-primary {
    background: var(--accent);
    color: #fff;
}
.btn-primary:hover { background: var(--accent-dark); transform: scale(1.015); }
.btn-primary:active { transform: scale(0.98); }

.btn-glass {
    background: var(--glass);
    border: 1px solid var(--glass-border);
    color: var(--text);
}
.btn-glass:hover { background: var(--glass-hover); border-color: rgba(255,255,255,0.2); }

.btn-gold {
    background: linear-gradient(135deg, #ffd60a, #ff9f0a);
    color: #000;
    font-weight: 600;
}
.btn-gold:hover { opacity: .9; transform: scale(1.015); }

.badge {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 4px 10px;
    border-radius: 20px;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: .02em;
    text-transform: uppercase;
}

.badge-pro {
    background: rgba(255,214,10,0.15);
    border: 1px solid rgba(255,214,10,0.3);
    color: var(--gold);
}

.badge-free {
    background: rgba(255,255,255,0.06);
    border: 1px solid rgba(255,255,255,0.1);
    color: var(--text-2);
}

@keyframes fadeUp {
    from { opacity: 0; transform: translateY(20px); }
    to   { opacity: 1; transform: translateY(0); }
}

@keyframes fadeIn {
    from { opacity: 0; }
    to   { opacity: 1; }
}

.anim { animation: fadeUp .5s ease both; }
.anim-1 { animation-delay: .05s; }
.anim-2 { animation-delay: .1s; }
.anim-3 { animation-delay: .15s; }
.anim-4 { animation-delay: .2s; }

/* Glow orbs background effect */
.orb {
    position: fixed;
    border-radius: 50%;
    filter: blur(80px);
    pointer-events: none;
    z-index: 0;
}
.orb-1 {
    width: 500px; height: 500px;
    top: -150px; left: -100px;
    background: radial-gradient(circle, rgba(41,151,255,0.12), transparent 70%);
}
.orb-2 {
    width: 400px; height: 400px;
    bottom: -100px; right: -50px;
    background: radial-gradient(circle, rgba(120,40,200,0.1), transparent 70%);
}

.content { position: relative; z-index: 1; }
"""

def page(title, body, navbar=True):
    nav = ""
    if navbar:
        nav = """
        <nav style="position:fixed;top:0;left:0;right:0;z-index:100;
            backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);
            background:rgba(0,0,0,0.7);border-bottom:1px solid rgba(255,255,255,0.07);
            padding:0 24px;height:52px;display:flex;align-items:center;justify-content:space-between;">
            <a href="/dashboard" style="font-size:17px;font-weight:600;letter-spacing:-.03em;">
                <span style="color:#fff;">Snap</span><span style="color:#2997ff;">2See</span>
            </a>
            <div style="display:flex;gap:8px;align-items:center;">
                <a href="/manage" class="btn btn-glass" style="padding:7px 16px;font-size:13px;">My QRs</a>
                <a href="/upgrade" class="btn btn-gold" style="padding:7px 16px;font-size:13px;">✦ Pro</a>
            </div>
        </nav>
        <div style="height:52px;"></div>
        """
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} — Snap2See</title>
<style>{BASE_CSS}</style>
</head>
<body>
<div class="orb orb-1"></div>
<div class="orb orb-2"></div>
{nav}
<div class="content">{body}</div>
</body>
</html>"""


# ── SPLASH ─────────────────────────────────────────────────────────────────────
@app.route("/")
def splash():
    body = """
    <style>
    @keyframes logoIn {
        0%   { opacity:0; transform:scale(.7) translateY(30px); }
        60%  { transform:scale(1.04) translateY(-4px); }
        100% { opacity:1; transform:scale(1) translateY(0); }
    }
    @keyframes pulse-ring {
        0%   { transform:scale(1);   opacity:.6; }
        100% { transform:scale(1.8); opacity:0; }
    }
    @keyframes float {
        0%,100% { transform:translateY(0px);   }
        50%      { transform:translateY(-10px); }
    }
    @keyframes shimmer {
        0%   { background-position: -200% center; }
        100% { background-position:  200% center; }
    }
    .splash-wrap {
        min-height:100vh;
        display:flex;
        flex-direction:column;
        align-items:center;
        justify-content:center;
        text-align:center;
        padding:40px 24px;
    }
    .logo-wrap {
        position:relative;
        margin-bottom:40px;
        animation: float 6s ease-in-out infinite;
    }
    .logo-icon {
        width:100px;height:100px;
        border-radius:28px;
        background: linear-gradient(145deg,#1a1a2e,#16213e,#0f3460);
        border:1px solid rgba(41,151,255,0.3);
        display:flex;align-items:center;justify-content:center;
        font-size:48px;
        position:relative;
        z-index:2;
        animation: logoIn .8s cubic-bezier(.34,1.56,.64,1) both;
        box-shadow: 0 20px 60px rgba(41,151,255,0.2), inset 0 1px 0 rgba(255,255,255,0.1);
    }
    .ring {
        position:absolute;top:50%;left:50%;
        width:100px;height:100px;
        margin:-50px 0 0 -50px;
        border-radius:50%;
        border:2px solid rgba(41,151,255,0.3);
        animation:pulse-ring 2.5s ease-out infinite;
    }
    .ring:nth-child(2){animation-delay:.8s;}
    .ring:nth-child(3){animation-delay:1.6s;}
    .logo-text {
        font-size:52px;
        font-weight:700;
        letter-spacing:-.04em;
        line-height:1;
        margin-bottom:16px;
        background: linear-gradient(90deg,#fff 30%,#2997ff 50%,#fff 70%);
        background-size:200% auto;
        -webkit-background-clip:text;
        -webkit-text-fill-color:transparent;
        background-clip:text;
        animation: shimmer 3s linear infinite, fadeUp .6s .3s ease both;
    }
    .logo-sub {
        font-size:19px;
        color: rgba(255,255,255,0.5);
        letter-spacing:.01em;
        margin-bottom:48px;
        animation: fadeUp .6s .45s ease both;
        opacity:0;animation-fill-mode:forwards;
    }
    .pill-row {
        display:flex;gap:12px;flex-wrap:wrap;justify-content:center;
        margin-bottom:48px;
        animation: fadeUp .6s .55s ease both;
        opacity:0;animation-fill-mode:forwards;
    }
    .pill {
        padding:6px 14px;
        border-radius:20px;
        font-size:13px;
        background:rgba(255,255,255,0.06);
        border:1px solid rgba(255,255,255,0.1);
        color:rgba(255,255,255,0.6);
    }
    .cta-wrap {
        display:flex;gap:12px;flex-wrap:wrap;justify-content:center;
        animation: fadeUp .6s .65s ease both;
        opacity:0;animation-fill-mode:forwards;
    }
    .hero-img {
        width:320px;
        height:200px;
        border-radius:20px;
        background:var(--bg-2);
        border:1px solid var(--glass-border);
        display:flex;align-items:center;justify-content:center;
        margin:60px auto 0;
        position:relative;
        overflow:hidden;
        animation: fadeUp .6s .8s ease both;
        opacity:0;animation-fill-mode:forwards;
    }
    .scan-line {
        position:absolute;
        left:0;right:0;height:2px;
        background:linear-gradient(90deg,transparent,var(--accent),transparent);
        top:0;
        animation:scan 3s ease-in-out infinite;
    }
    @keyframes scan {
        0%,100%{top:10%} 50%{top:85%}
    }
    .qr-demo {
        width:80px;height:80px;
        display:grid;grid-template-columns:repeat(7,1fr);
        gap:2px;
    }
    .qr-c { border-radius:1px; }
    </style>

    <div class="splash-wrap">
        <div class="logo-wrap">
            <div class="ring"></div>
            <div class="ring"></div>
            <div class="ring"></div>
            <div class="logo-icon">⊞</div>
        </div>

        <div class="logo-text">Snap2See</div>
        <div class="logo-sub">Smart QR codes. Anywhere. Anytime.</div>

        <div class="pill-row">
            <div class="pill">📊 Scan Analytics</div>
            <div class="pill">🔄 Dynamic Content</div>
            <div class="pill">⚡ Instant Deploy</div>
            <div class="pill">🔐 Secure Links</div>
        </div>

        <div class="cta-wrap">
            <a href="/login" class="btn btn-primary" style="padding:16px 36px;font-size:17px;border-radius:16px;
                box-shadow:0 8px 32px rgba(41,151,255,0.4);">
                Get Started
            </a>
            <a href="/login" class="btn btn-glass" style="padding:16px 36px;font-size:17px;border-radius:16px;">
                Sign In
            </a>
        </div>

        <div class="hero-img">
            <div class="scan-line"></div>
            <div style="text-align:center;">
                <div style="font-size:48px;opacity:.15;letter-spacing:4px;font-family:monospace;">
                ▓▓░▓░▓▓<br>▓░░░░░▓<br>▓░▓▓▓░▓<br>░░▓░▓░░<br>▓░▓▓▓░▓<br>▓░░░░░▓<br>▓▓░▓░▓▓
                </div>
                <p style="font-size:12px;color:var(--text-3);margin-top:12px;position:relative;z-index:2;">
                    Scan to view live content
                </p>
            </div>
        </div>
    </div>
    """
    return page("Welcome", body, navbar=False)


# ── LOGIN ──────────────────────────────────────────────────────────────────────
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

    body = """
    <style>
    .login-wrap {
        min-height:100vh;
        display:flex;
        align-items:center;
        justify-content:center;
        padding:24px;
    }
    .login-card {
        width:100%;max-width:400px;
        border-radius:var(--radius-xl);
        padding:40px;
    }
    </style>
    <div class="login-wrap">
        <div class="login-card glass anim">
            <div style="text-align:center;margin-bottom:32px;">
                <div style="font-size:36px;margin-bottom:12px;">⊞</div>
                <h1 style="font-size:26px;font-weight:700;letter-spacing:-.03em;margin-bottom:6px;">Sign in</h1>
                <p style="color:var(--text-2);font-size:14px;">to Snap2See — or create an account</p>
            </div>

            <form method="post">
                <div style="display:flex;flex-direction:column;gap:12px;margin-bottom:20px;">
                    <input type="text" name="username" placeholder="Username" required autofocus>
                    <input type="password" name="password" placeholder="Password" required>
                </div>
                <button type="submit" class="btn btn-primary" style="width:100%;padding:14px;">
                    Continue →
                </button>
            </form>

            <p style="text-align:center;font-size:12px;color:var(--text-3);margin-top:20px;">
                New here? Entering your details creates an account automatically.
            </p>

            <div style="margin-top:24px;padding-top:24px;border-top:1px solid var(--glass-border);text-align:center;">
                <a href="/" style="font-size:13px;color:var(--text-3);">← Back to home</a>
            </div>
        </div>
    </div>
    """
    return page("Sign In", body, navbar=False)


# ── DASHBOARD ─────────────────────────────────────────────────────────────────
@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect("/login")
    c.execute("SELECT is_pro, username FROM users WHERE id=?", (session["user_id"],))
    row = c.fetchone()
    pro, username = row[0], row[1]

    c.execute("SELECT COUNT(*) FROM files WHERE user_id=?", (session["user_id"],))
    qr_count = c.fetchone()[0]

    c.execute("SELECT SUM(scans) FROM files WHERE user_id=?", (session["user_id"],))
    total_scans = c.fetchone()[0] or 0

    pro_badge = '<span class="badge badge-pro">✦ Pro</span>' if pro else '<span class="badge badge-free">Free</span>'

    body = f"""
    <style>
    .dash-wrap {{ max-width:800px;margin:0 auto;padding:40px 24px; }}
    .stat-grid {{
        display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));
        gap:12px;margin-bottom:32px;
    }}
    .stat-card {{
        border-radius:var(--radius-lg);
        padding:20px;
    }}
    .upload-zone {{
        border-radius:var(--radius-xl);
        padding:40px;
        text-align:center;
        transition:border-color .2s,background .2s;
        cursor:pointer;
    }}
    .upload-zone:hover {{ background:rgba(255,255,255,0.06); }}
    </style>

    <div class="dash-wrap">
        <!-- Header -->
        <div style="display:flex;align-items:flex-start;justify-content:space-between;
            margin-bottom:32px;" class="anim">
            <div>
                <p style="color:var(--text-2);font-size:14px;margin-bottom:4px;">Welcome back,</p>
                <h1 style="font-size:30px;font-weight:700;letter-spacing:-.03em;">{username}</h1>
            </div>
            {pro_badge}
        </div>

        <!-- Stats -->
        <div class="stat-grid anim anim-1">
            <div class="stat-card glass">
                <div style="font-size:13px;color:var(--text-2);margin-bottom:8px;">QR Codes</div>
                <div style="font-size:32px;font-weight:700;letter-spacing:-.03em;">{qr_count}</div>
                <div style="font-size:12px;color:var(--text-3);margin-top:4px;">total created</div>
            </div>
            <div class="stat-card glass">
                <div style="font-size:13px;color:var(--text-2);margin-bottom:8px;">Total Scans</div>
                <div style="font-size:32px;font-weight:700;letter-spacing:-.03em;color:var(--accent);">{total_scans}</div>
                <div style="font-size:12px;color:var(--text-3);margin-top:4px;">all time</div>
            </div>
            <div class="stat-card glass">
                <div style="font-size:13px;color:var(--text-2);margin-bottom:8px;">Plan</div>
                <div style="font-size:28px;font-weight:700;letter-spacing:-.03em;
                    color:{'var(--gold)' if pro else 'var(--text-2)'};">
                    {"Pro" if pro else "Free"}
                </div>
                <div style="font-size:12px;color:var(--text-3);margin-top:4px;">
                    {"unlimited QRs" if pro else "upgrade for more"}
                </div>
            </div>
        </div>

        <!-- Upload -->
        <div class="glass anim anim-2" style="border-radius:var(--radius-xl);padding:32px;margin-bottom:24px;">
            <h2 style="font-size:19px;font-weight:600;letter-spacing:-.02em;margin-bottom:6px;">
                Create QR Code
            </h2>
            <p style="color:var(--text-2);font-size:14px;margin-bottom:24px;">
                Upload any file — image, PDF, video — and get a scannable QR instantly.
            </p>
            <form action="/upload" method="post" enctype="multipart/form-data">
                <div style="margin-bottom:16px;">
                    <input type="file" name="file" required>
                </div>
                <button type="submit" class="btn btn-primary" style="width:100%;padding:14px;">
                    ⊕ Generate QR Code
                </button>
            </form>
        </div>

        <!-- Quick links -->
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;" class="anim anim-3">
            <a href="/manage" class="btn btn-glass" style="padding:16px;border-radius:var(--radius-lg);">
                <span style="font-size:20px;">⊟</span>
                <div style="text-align:left;">
                    <div style="font-size:14px;font-weight:500;">My QR Codes</div>
                    <div style="font-size:12px;color:var(--text-2);">View & manage</div>
                </div>
            </a>
            {'<a href="/manage" class="btn btn-glass" style="padding:16px;border-radius:var(--radius-lg);"><span style="font-size:20px;">📊</span><div style="text-align:left;"><div style="font-size:14px;font-weight:500;">Analytics</div><div style="font-size:12px;color:var(--text-2);">Scan stats</div></div></a>'
            if pro else
            '<a href="/upgrade" class="btn" style="padding:16px;border-radius:var(--radius-lg);background:rgba(255,214,10,0.08);border:1px solid rgba(255,214,10,0.2);"><span style="font-size:20px;">✦</span><div style="text-align:left;"><div style="font-size:14px;font-weight:500;color:var(--gold);">Upgrade to Pro</div><div style="font-size:12px;color:var(--text-2);">Unlock analytics</div></div></a>'}
        </div>
    </div>
    """
    return page("Dashboard", body)


# ── UPGRADE ───────────────────────────────────────────────────────────────────
@app.route("/upgrade", methods=["GET", "POST"])
def upgrade():
    if "user_id" not in session:
        return redirect("/login")

    if request.method == "POST":
        c.execute("UPDATE users SET is_pro=1 WHERE id=?", (session["user_id"],))
        conn.commit()
        return redirect("/dashboard")

    body = """
    <style>
    .upgrade-wrap { max-width:560px;margin:0 auto;padding:60px 24px;text-align:center; }
    .plan-card {
        border-radius:var(--radius-xl);
        padding:32px;
        margin-bottom:16px;
        text-align:left;
        position:relative;
        overflow:hidden;
    }
    .feature-row {
        display:flex;align-items:center;gap:10px;
        padding:10px 0;
        border-bottom:1px solid rgba(255,255,255,0.06);
        font-size:14px;color:var(--text-2);
    }
    .feature-row:last-child { border-bottom:none; }
    .check { color:var(--green);font-size:15px; }
    </style>

    <div class="upgrade-wrap">
        <div class="anim" style="margin-bottom:40px;">
            <div style="font-size:40px;margin-bottom:16px;">✦</div>
            <h1 style="font-size:32px;font-weight:700;letter-spacing:-.03em;margin-bottom:10px;">
                Unlock Snap2See Pro
            </h1>
            <p style="color:var(--text-2);font-size:16px;">
                Everything you need for powerful QR campaigns.
            </p>
        </div>

        <div class="plan-card anim anim-1" style="background:rgba(255,214,10,0.05);
            border:1px solid rgba(255,214,10,0.25);">
            <div style="position:absolute;top:0;right:0;width:200px;height:200px;
                background:radial-gradient(circle,rgba(255,214,10,0.08),transparent);
                pointer-events:none;"></div>

            <div style="display:flex;justify-content:space-between;align-items:flex-start;
                margin-bottom:24px;">
                <div>
                    <div style="font-size:13px;color:var(--gold);font-weight:600;
                        letter-spacing:.05em;text-transform:uppercase;margin-bottom:6px;">
                        Pro Plan
                    </div>
                    <div style="font-size:38px;font-weight:700;letter-spacing:-.04em;">
                        $10
                        <span style="font-size:16px;font-weight:400;color:var(--text-2);">/mo</span>
                    </div>
                </div>
                <span class="badge badge-pro">Most Popular</span>
            </div>

            <div>
                <div class="feature-row">
                    <span class="check">✓</span> Unlimited QR codes
                </div>
                <div class="feature-row">
                    <span class="check">✓</span> Dynamic content updates
                </div>
                <div class="feature-row">
                    <span class="check">✓</span> Advanced scan analytics
                </div>
                <div class="feature-row">
                    <span class="check">✓</span> Custom branding & styling
                </div>
                <div class="feature-row">
                    <span class="check">✓</span> Priority support
                </div>
                <div class="feature-row">
                    <span class="check">✓</span> Bulk QR generation
                </div>
            </div>

            <form method="post" style="margin-top:24px;">
                <button type="submit" class="btn btn-gold" style="width:100%;padding:15px;font-size:16px;">
                    Activate Pro (Demo) →
                </button>
            </form>
        </div>

        <a href="/dashboard" style="font-size:13px;color:var(--text-3);">← Back to dashboard</a>
    </div>
    """
    return page("Upgrade", body)


# ── UPLOAD + QR ───────────────────────────────────────────────────────────────
@app.route("/upload", methods=["POST"])
def upload():
    if "user_id" not in session:
        return redirect("/login")
    file = request.files["file"]
    file_id = str(uuid.uuid4())
    filename = file_id + "_" + file.filename
    path = os.path.join(UPLOADS, filename)
    file.save(path)
    c.execute("INSERT INTO files (id, user_id, filename, created) VALUES (?,?,?,?)",
              (file_id, session["user_id"], filename, datetime.now()))
    conn.commit()
    base = request.host_url.strip("/")
    link = f"{base}/view/{file_id}"
    img = qrcode.make(link)
    qr_path = os.path.join(QRS, file_id + ".png")
    img.save(qr_path)

    body = f"""
    <style>
    .success-wrap {{ max-width:500px;margin:0 auto;padding:60px 24px;text-align:center; }}
    </style>
    <div class="success-wrap">
        <div class="anim" style="font-size:48px;margin-bottom:20px;">✓</div>

        <h1 class="anim anim-1" style="font-size:28px;font-weight:700;letter-spacing:-.03em;
            margin-bottom:10px;color:var(--green);">QR Created!</h1>

        <p class="anim anim-2" style="color:var(--text-2);margin-bottom:32px;font-size:15px;">
            Your QR code is live and ready to scan.
        </p>

        <div class="glass anim anim-2" style="border-radius:var(--radius-xl);padding:32px;
            display:inline-block;margin-bottom:24px;">
            <img src="/qr/{file_id}" width="200" height="200"
                style="border-radius:12px;display:block;">
        </div>

        <div class="glass anim anim-3" style="border-radius:var(--radius-lg);
            padding:14px 18px;margin-bottom:28px;word-break:break-all;">
            <div style="font-size:11px;color:var(--text-3);margin-bottom:6px;
                text-transform:uppercase;letter-spacing:.05em;">QR Link</div>
            <div style="font-size:13px;color:var(--accent);">{link}</div>
        </div>

        <div class="anim anim-4" style="display:flex;gap:12px;justify-content:center;flex-wrap:wrap;">
            <a href="/dashboard" class="btn btn-primary">← Dashboard</a>
            <a href="/manage" class="btn btn-glass">View All QRs</a>
        </div>
    </div>
    """
    return page("QR Created", body)


# ── QR IMAGE ──────────────────────────────────────────────────────────────────
@app.route("/qr/<id>")
def qr(id):
    return send_file(os.path.join(QRS, id + ".png"))


# ── VIEW FILE ─────────────────────────────────────────────────────────────────
@app.route("/view/<id>")
def view(id):
    c.execute("SELECT filename FROM files WHERE id=?", (id,))
    data = c.fetchone()
    if not data:
        return "Not found", 404
    filename = data[0]
    c.execute("UPDATE files SET scans = scans + 1 WHERE id=?", (id,))
    conn.commit()
    return send_file(os.path.join(UPLOADS, filename))


# ── MANAGE QR ─────────────────────────────────────────────────────────────────
@app.route("/manage")
def manage():
    if "user_id" not in session:
        return redirect("/login")
    c.execute("SELECT id, filename, scans, created FROM files WHERE user_id=? ORDER BY created DESC",
              (session["user_id"],))
    rows = c.fetchall()

    if not rows:
        cards = """
        <div class="glass" style="border-radius:var(--radius-xl);padding:60px 32px;text-align:center;">
            <div style="font-size:48px;margin-bottom:16px;opacity:.3;">⊞</div>
            <p style="color:var(--text-2);margin-bottom:24px;">No QR codes yet.</p>
            <a href="/dashboard" class="btn btn-primary">Create your first QR</a>
        </div>
        """
    else:
        cards = '<div style="display:flex;flex-direction:column;gap:12px;">'
        for r in rows:
            orig_name = r[1].split("_", 1)[1] if "_" in r[1] else r[1]
            created = r[3][:10] if r[3] else "—"
            cards += f"""
            <div class="glass" style="border-radius:var(--radius-lg);padding:20px 24px;
                display:flex;align-items:center;gap:16px;">
                <img src="/qr/{r[0]}" width="60" height="60"
                    style="border-radius:8px;border:1px solid var(--glass-border);">
                <div style="flex:1;min-width:0;">
                    <div style="font-size:14px;font-weight:500;margin-bottom:3px;
                        overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{orig_name}</div>
                    <div style="font-size:12px;color:var(--text-3);">Created {created}</div>
                </div>
                <div style="text-align:center;min-width:60px;">
                    <div style="font-size:22px;font-weight:700;color:var(--accent);">{r[2]}</div>
                    <div style="font-size:11px;color:var(--text-3);">scans</div>
                </div>
                <div style="display:flex;gap:8px;flex-shrink:0;">
                    <a href="/view/{r[0]}" class="btn btn-glass" style="padding:8px 14px;font-size:13px;">
                        Open
                    </a>
                    <a href="/edit/{r[0]}" class="btn btn-glass" style="padding:8px 14px;font-size:13px;">
                        Edit
                    </a>
                </div>
            </div>
            """
        cards += "</div>"

    body = f"""
    <div style="max-width:700px;margin:0 auto;padding:40px 24px;">
        <div style="display:flex;align-items:center;justify-content:space-between;
            margin-bottom:32px;" class="anim">
            <h1 style="font-size:28px;font-weight:700;letter-spacing:-.03em;">My QR Codes</h1>
            <a href="/dashboard" class="btn btn-primary" style="padding:10px 18px;font-size:13px;">
                + New QR
            </a>
        </div>
        <div class="anim anim-1">{cards}</div>
    </div>
    """
    return page("My QRs", body)


# ── EDIT QR ───────────────────────────────────────────────────────────────────
@app.route("/edit/<id>", methods=["GET", "POST"])
def edit(id):
    if "user_id" not in session:
        return redirect("/login")
    if request.method == "POST":
        file = request.files["file"]
        c.execute("SELECT filename FROM files WHERE id=?", (id,))
        old = c.fetchone()[0]
        path = os.path.join(UPLOADS, old)
        file.save(path)
        return redirect("/manage")

    body = f"""
    <div style="max-width:480px;margin:0 auto;padding:60px 24px;">
        <div class="glass anim" style="border-radius:var(--radius-xl);padding:40px;">
            <div style="font-size:30px;margin-bottom:16px;text-align:center;">🔄</div>
            <h1 style="font-size:24px;font-weight:700;letter-spacing:-.03em;
                margin-bottom:8px;text-align:center;">Replace File</h1>
            <p style="color:var(--text-2);font-size:14px;text-align:center;
                margin-bottom:28px;">
                The QR code URL stays the same — only the content changes.
            </p>

            <div class="glass" style="border-radius:var(--radius);padding:12px;
                margin-bottom:16px;display:flex;align-items:center;gap:10px;">
                <span style="font-size:18px;">ℹ️</span>
                <div>
                    <div style="font-size:12px;font-weight:500;margin-bottom:2px;">QR ID</div>
                    <div style="font-size:11px;color:var(--text-3);font-family:monospace;">{id}</div>
                </div>
            </div>

            <form method="post" enctype="multipart/form-data">
                <div style="margin-bottom:16px;">
                    <input type="file" name="file" required>
                </div>
                <button type="submit" class="btn btn-primary" style="width:100%;padding:14px;">
                    Update Content →
                </button>
            </form>

            <div style="text-align:center;margin-top:20px;">
                <a href="/manage" style="font-size:13px;color:var(--text-3);">← Cancel</a>
            </div>
        </div>
    </div>
    """
    return page("Edit QR", body)


# ── RUN ────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
