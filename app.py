from flask import Flask, request, redirect, session, send_file
import sqlite3, os, uuid, qrcode
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

app = Flask(__name__)
app.secret_key = "snap2see-secret-key-2024"

UPLOADS    = "uploads"
QRS        = "qrs"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

os.makedirs(UPLOADS, exist_ok=True)
os.makedirs(QRS,     exist_ok=True)

# ── DATABASE ──────────────────────────────────────────────────────────────────
conn = sqlite3.connect("app.db", check_same_thread=False)
c    = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS users (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    password TEXT,
    is_pro   INTEGER DEFAULT 0
)""")

c.execute("""
CREATE TABLE IF NOT EXISTS files (
    id       TEXT PRIMARY KEY,
    user_id  INTEGER,
    filename TEXT,
    scans    INTEGER DEFAULT 0,
    created  TEXT
)""")
conn.commit()


# ── WATERMARK ─────────────────────────────────────────────────────────────────
def apply_watermark(path, text="Snap2See"):
    ext = os.path.splitext(path)[1].lower()
    if ext not in IMAGE_EXTS:
        return False
    try:
        img     = Image.open(path).convert("RGBA")
        w, h    = img.size
        layer   = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw    = ImageDraw.Draw(layer)
        fsize   = max(14, min(w, h) // 18)
        try:
            font = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", fsize)
        except Exception:
            font = ImageFont.load_default()
        bbox   = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        pad    = 14
        x, y   = w - tw - pad, h - th - pad
        draw.rectangle([x - 8, y - 6, x + tw + 8, y + th + 6], fill=(0, 0, 0, 120))
        draw.text((x, y), text, font=font, fill=(255, 255, 255, 220))
        out = Image.alpha_composite(img, layer).convert("RGB")
        out.save(path)
        return True
    except Exception:
        return False


# ── SHARED CSS ────────────────────────────────────────────────────────────────
BASE_CSS = """
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0;}
:root{
    --bg:#000;--bg1:#0c0c0e;--bg2:#141416;--bg3:#1c1c1f;
    --glass:rgba(255,255,255,0.035);--glassmd:rgba(255,255,255,0.06);
    --gb:rgba(255,255,255,0.09);--gbmd:rgba(255,255,255,0.16);
    --t:#f2f2f7;--t2:#98989f;--t3:#58585f;
    --ac:#2997ff;--acdk:#0070d4;--acg:rgba(41,151,255,0.25);
    --gold:#ffd60a;--golddk:#e6c000;
    --green:#32d74b;--red:#ff453a;
    --rsm:10px;--rmd:16px;--rlg:22px;--rxl:30px;
}
html{scroll-behavior:smooth;}
body{
    background:var(--bg);color:var(--t);
    font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text","Helvetica Neue",Arial,sans-serif;
    min-height:100vh;-webkit-font-smoothing:antialiased;line-height:1.5;
}
a{color:inherit;text-decoration:none;}
.glass{background:var(--glass);border:1px solid var(--gb);
    backdrop-filter:blur(24px);-webkit-backdrop-filter:blur(24px);}
.glassmd{background:var(--glassmd);border:1px solid var(--gbmd);
    backdrop-filter:blur(24px);-webkit-backdrop-filter:blur(24px);}
input[type=text],input[type=password]{
    width:100%;padding:13px 16px;background:rgba(255,255,255,0.05);
    border:1px solid var(--gb);border-radius:var(--rmd);
    color:var(--t);font-size:15px;font-family:inherit;outline:none;
    transition:border-color .18s,box-shadow .18s;
}
input[type=text]:focus,input[type=password]:focus{
    border-color:var(--ac);box-shadow:0 0 0 3px var(--acg);}
input::placeholder{color:var(--t3);}
input[type=file]{display:none;}
.filedrop{
    width:100%;padding:32px 20px;background:rgba(255,255,255,0.03);
    border:1.5px dashed rgba(255,255,255,0.12);border-radius:var(--rlg);
    color:var(--t2);font-size:14px;font-family:inherit;
    outline:none;cursor:pointer;transition:border-color .2s,background .2s;
    display:block;text-align:center;
}
.filedrop:hover{border-color:var(--ac);background:rgba(41,151,255,0.05);}
.btn{
    display:inline-flex;align-items:center;justify-content:center;gap:7px;
    padding:12px 22px;border-radius:var(--rmd);font-size:15px;font-weight:500;
    cursor:pointer;border:none;transition:all .18s cubic-bezier(.25,.46,.45,.94);
    font-family:inherit;letter-spacing:-.01em;white-space:nowrap;
}
.btnp{background:var(--ac);color:#fff;box-shadow:0 4px 20px rgba(41,151,255,0.3);}
.btnp:hover{background:var(--acdk);transform:translateY(-1px);}
.btnp:active{transform:scale(.98);}
.btng{background:var(--glass);border:1px solid var(--gb);color:var(--t);}
.btng:hover{background:var(--glassmd);border-color:var(--gbmd);}
.btngold{background:var(--gold);color:#000;font-weight:600;
    box-shadow:0 4px 20px rgba(255,214,10,0.25);}
.btngold:hover{background:var(--golddk);transform:translateY(-1px);}
.btnsm{padding:7px 14px;font-size:13px;border-radius:var(--rsm);}
.badge{display:inline-flex;align-items:center;padding:3px 9px;border-radius:20px;
    font-size:11px;font-weight:600;letter-spacing:.04em;text-transform:uppercase;}
.badgepro{background:rgba(255,214,10,0.12);border:1px solid rgba(255,214,10,0.25);color:var(--gold);}
.badgefree{background:rgba(255,255,255,0.05);border:1px solid var(--gb);color:var(--t3);}
@keyframes fadeUp{from{opacity:0;transform:translateY(18px);}to{opacity:1;transform:translateY(0);}}
.a0{animation:fadeUp .45s ease both;}
.a1{animation:fadeUp .45s .07s ease both;}
.a2{animation:fadeUp .45s .14s ease both;}
.a3{animation:fadeUp .45s .21s ease both;}
.a4{animation:fadeUp .45s .28s ease both;}
.orb{position:fixed;border-radius:50%;pointer-events:none;z-index:0;}
.orb1{width:600px;height:600px;top:-200px;left:-150px;
    background:radial-gradient(circle,rgba(41,151,255,0.09) 0%,transparent 65%);}
.orb2{width:500px;height:500px;bottom:-150px;right:-100px;
    background:radial-gradient(circle,rgba(100,40,180,0.08) 0%,transparent 65%);}
.con{position:relative;z-index:1;}
.divider{border:none;border-top:1px solid var(--gb);margin:0;}
.stat{border-radius:var(--rlg);padding:20px 22px;background:var(--glass);border:1px solid var(--gb);}
.statval{font-size:34px;font-weight:700;letter-spacing:-.04em;line-height:1;margin-bottom:5px;}
.statlbl{font-size:12px;color:var(--t3);text-transform:uppercase;letter-spacing:.05em;font-weight:500;}
.pw{max-width:720px;margin:0 auto;padding:48px 24px 80px;}
"""

NAV_CSS = """
#nav{position:fixed;top:0;left:0;right:0;z-index:200;height:56px;
    display:flex;align-items:center;justify-content:space-between;padding:0 28px;
    background:rgba(0,0,0,0.75);border-bottom:1px solid rgba(255,255,255,0.07);
    backdrop-filter:blur(28px);-webkit-backdrop-filter:blur(28px);}
.navlogo{font-size:18px;font-weight:700;letter-spacing:-.04em;}
.navr{display:flex;gap:8px;align-items:center;}
"""

def page(title, body, navbar=True):
    nav = ""
    if navbar:
        nav = """
        <nav id="nav">
          <a href="/dashboard" class="navlogo">
            Snap<span style="color:var(--ac);">2See</span>
          </a>
          <div class="navr">
            <a href="/manage"  class="btn btng btnsm">My QRs</a>
            <a href="/upgrade" class="btn btngold btnsm">Pro</a>
          </div>
        </nav>
        <div style="height:56px;"></div>"""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} — Snap2See</title>
<style>{BASE_CSS}{NAV_CSS}</style>
</head>
<body>
<div class="orb orb1"></div>
<div class="orb orb2"></div>
{nav}
<div class="con">{body}</div>
</body>
</html>"""


# ── SPLASH ────────────────────────────────────────────────────────────────────
@app.route("/")
def splash():
    body = """
<style>
@keyframes logoReveal{
    0%{opacity:0;transform:scale(.7) translateY(28px);}
    65%{transform:scale(1.03) translateY(-3px);}
    100%{opacity:1;transform:scale(1) translateY(0);}
}
@keyframes ringExpand{
    0%{transform:scale(1);opacity:.5;}
    100%{transform:scale(2.2);opacity:0;}
}
@keyframes floatUp{
    0%,100%{transform:translateY(0);}
    50%{transform:translateY(-9px);}
}
@keyframes shimmerText{
    0%{background-position:0% center;}
    100%{background-position:200% center;}
}
.hero{min-height:100vh;display:flex;flex-direction:column;align-items:center;
    justify-content:center;text-align:center;padding:60px 24px 80px;}
.logoWrap{position:relative;width:120px;height:120px;margin:0 auto 40px;
    animation:floatUp 7s ease-in-out infinite;}
.ring{position:absolute;inset:0;border-radius:50%;
    border:1.5px solid rgba(41,151,255,0.35);animation:ringExpand 2.8s ease-out infinite;}
.ring:nth-child(2){animation-delay:.9s;}
.ring:nth-child(3){animation-delay:1.8s;}
.logoBox{position:relative;z-index:2;width:120px;height:120px;border-radius:32px;
    background:linear-gradient(145deg,#101828,#0d2340);
    border:1px solid rgba(41,151,255,0.25);
    box-shadow:0 24px 64px rgba(41,151,255,0.18),inset 0 1px 0 rgba(255,255,255,0.08);
    display:flex;align-items:center;justify-content:center;
    animation:logoReveal .9s cubic-bezier(.34,1.56,.64,1) both;}
.heroTitle{
    font-size:clamp(42px,8vw,64px);font-weight:700;letter-spacing:-.05em;
    line-height:1;margin-bottom:18px;
    background:linear-gradient(100deg,#ffffff 20%,#2997ff 50%,#ffffff 80%);
    background-size:200% auto;-webkit-background-clip:text;
    -webkit-text-fill-color:transparent;background-clip:text;
    animation:shimmerText 4s linear infinite, fadeUp .6s .2s ease both;
    opacity:0;animation-fill-mode:forwards;
}
.heroSub{font-size:18px;color:var(--t2);max-width:460px;margin:0 auto 44px;
    line-height:1.6;animation:fadeUp .6s .35s ease both;
    opacity:0;animation-fill-mode:forwards;}
.pillRow{display:flex;gap:10px;flex-wrap:wrap;justify-content:center;
    margin-bottom:48px;animation:fadeUp .6s .45s ease both;
    opacity:0;animation-fill-mode:forwards;}
.pill{padding:5px 14px;border-radius:20px;font-size:12px;font-weight:500;
    background:rgba(255,255,255,0.05);border:1px solid var(--gb);
    color:var(--t2);letter-spacing:.01em;}
.ctaRow{display:flex;gap:12px;flex-wrap:wrap;justify-content:center;
    animation:fadeUp .6s .55s ease both;opacity:0;animation-fill-mode:forwards;}

.section{padding:80px 24px;max-width:820px;margin:0 auto;}
.sectionLabel{font-size:11px;font-weight:600;letter-spacing:.1em;
    text-transform:uppercase;color:var(--ac);margin-bottom:14px;}
.sectionTitle{font-size:clamp(28px,5vw,38px);font-weight:700;
    letter-spacing:-.04em;margin-bottom:18px;line-height:1.15;}
.sectionBody{font-size:16px;color:var(--t2);line-height:1.75;}

.whyGrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));
    gap:16px;margin-top:40px;}
.whyCard{border-radius:var(--rlg);padding:24px;background:var(--glass);
    border:1px solid var(--gb);}
.whyIcon{width:36px;height:36px;border-radius:10px;
    background:rgba(41,151,255,0.12);border:1px solid rgba(41,151,255,0.2);
    display:flex;align-items:center;justify-content:center;margin-bottom:14px;}
.whyCard h3{font-size:15px;font-weight:600;margin-bottom:6px;letter-spacing:-.01em;}
.whyCard p{font-size:13px;color:var(--t2);line-height:1.6;}

.policyWrap{background:var(--bg1);border-top:1px solid var(--gb);}
.policyBlock{max-width:760px;margin:0 auto;padding:72px 24px 80px;}
.policyBlock h2{font-size:30px;font-weight:700;letter-spacing:-.03em;margin-bottom:6px;}
.policyUpdated{font-size:12px;color:var(--t3);margin-bottom:36px;}
.policyItem{margin-bottom:28px;padding-bottom:28px;border-bottom:1px solid var(--gb);}
.policyItem:last-child{border-bottom:none;margin-bottom:0;padding-bottom:0;}
.policyItem h3{font-size:16px;font-weight:600;letter-spacing:-.01em;margin-bottom:8px;}
.policyItem p{font-size:14px;color:var(--t2);line-height:1.75;}

footer{border-top:1px solid var(--gb);padding:24px;text-align:center;
    font-size:12px;color:var(--t3);}
footer a{color:var(--t3);}
footer a:hover{color:var(--t2);}
</style>

<!-- HERO -->
<section class="hero">
    <div class="logoWrap">
        <div class="ring"></div>
        <div class="ring"></div>
        <div class="ring"></div>
        <div class="logoBox">
            <svg width="54" height="54" viewBox="0 0 54 54" fill="none">
                <rect x="4"  y="4"  width="18" height="18" rx="3" stroke="#2997ff" stroke-width="2.5"/>
                <rect x="32" y="4"  width="18" height="18" rx="3" stroke="#2997ff" stroke-width="2.5"/>
                <rect x="4"  y="32" width="18" height="18" rx="3" stroke="#2997ff" stroke-width="2.5"/>
                <rect x="8"  y="8"  width="10" height="10" rx="1.5" fill="#2997ff"/>
                <rect x="36" y="8"  width="10" height="10" rx="1.5" fill="#2997ff"/>
                <rect x="8"  y="36" width="10" height="10" rx="1.5" fill="#2997ff"/>
                <rect x="32" y="32" width="5"  height="5"  rx="1" fill="#2997ff"/>
                <rect x="41" y="32" width="9"  height="5"  rx="1" fill="rgba(41,151,255,.5)"/>
                <rect x="32" y="41" width="18" height="5"  rx="1" fill="rgba(41,151,255,.5)"/>
            </svg>
        </div>
    </div>

    <h1 class="heroTitle">Snap2See</h1>
    <p class="heroSub">
        Upload any file. Get a smart QR code instantly.<br>
        Track every scan in real time.
    </p>

    <div class="pillRow">
        <div class="pill">Scan Analytics</div>
        <div class="pill">Dynamic Content</div>
        <div class="pill">Instant Deploy</div>
        <div class="pill">Auto Watermarking</div>
        <div class="pill">Secure Links</div>
    </div>

    <div class="ctaRow">
        <a href="/login" class="btn btnp"
            style="padding:15px 36px;font-size:16px;border-radius:var(--rlg);">
            Get Started
        </a>
        <a href="#why" class="btn btng"
            style="padding:15px 36px;font-size:16px;border-radius:var(--rlg);">
            Learn More
        </a>
    </div>
</section>

<!-- WHY WE BUILT THIS -->
<div style="border-top:1px solid var(--gb);">
<section class="section" id="why">
    <div class="sectionLabel">Our Story</div>
    <h2 class="sectionTitle">Why we built Snap2See</h2>
    <p class="sectionBody">
        We got frustrated with QR codes that broke the moment a link changed. You print a
        hundred flyers, then update your menu or portfolio — and suddenly every QR is useless.
        Snap2See solves that: the physical QR code you print today can serve entirely different
        content tomorrow, with no reprinting required.
    </p>
    <p class="sectionBody" style="margin-top:16px;">
        We also believed every image shared via QR should carry its source with it. Watermarking
        is automatic and invisible to set up — protecting creators without any extra steps.
        Analytics are built in from day one, because knowing how people engage with your content
        matters whether you are a freelancer, a restaurant owner, or a growing team.
    </p>

    <div class="whyGrid">
        <div class="whyCard">
            <div class="whyIcon">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
                    stroke="#2997ff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="3" y="3" width="7" height="7" rx="1"/>
                    <rect x="14" y="3" width="7" height="7" rx="1"/>
                    <rect x="3" y="14" width="7" height="7" rx="1"/>
                    <rect x="14" y="14" width="7" height="7" rx="1"/>
                </svg>
            </div>
            <h3>Dynamic QR Codes</h3>
            <p>The URL printed on paper never changes. The file it delivers can be swapped any time from your dashboard.</p>
        </div>
        <div class="whyCard">
            <div class="whyIcon">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
                    stroke="#2997ff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
                </svg>
            </div>
            <h3>Creator Protection</h3>
            <p>Every image file receives a Snap2See watermark automatically, so credit follows your work wherever it travels.</p>
        </div>
        <div class="whyCard">
            <div class="whyIcon">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
                    stroke="#2997ff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
                </svg>
            </div>
            <h3>Real-Time Analytics</h3>
            <p>Watch your scan count grow with every visit. Know which QR codes are performing and which need attention.</p>
        </div>
        <div class="whyCard">
            <div class="whyIcon">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
                    stroke="#2997ff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="3" y="11" width="18" height="11" rx="2"/>
                    <path d="M7 11V7a5 5 0 0110 0v4"/>
                </svg>
            </div>
            <h3>Private by Default</h3>
            <p>Files are accessible only through unique randomly generated links embedded in your QR code — nothing is publicly indexed.</p>
        </div>
    </div>
</section>
</div>

<!-- PRIVACY POLICY -->
<div class="policyWrap" id="privacy">
    <div class="policyBlock">
        <div class="sectionLabel">Legal</div>
        <h2>Privacy Policy</h2>
        <p class="policyUpdated">Last updated: January 2025</p>

        <div class="policyItem">
            <h3>Information We Collect</h3>
            <p>We collect the username and password you provide at registration, the files you upload
            to generate QR codes, and aggregate scan count data — a number only, not identifying
            information about who scanned. We do not collect email addresses, phone numbers, or
            payment information beyond what a future payment processor would handle independently.</p>
        </div>
        <div class="policyItem">
            <h3>How We Use Your Data</h3>
            <p>Your uploaded files are stored solely to serve them when a QR code is scanned.
            Scan counts are used to display analytics on your dashboard. We do not sell, rent,
            or share any of your data with third parties for advertising or profiling purposes.</p>
        </div>
        <div class="policyItem">
            <h3>File Storage and Watermarking</h3>
            <p>Files are stored on the server running this application. Images are automatically
            watermarked with "Snap2See" before being saved, to protect creator attribution.
            You retain full ownership of all files you upload. You may delete any file at any
            time from the Manage QRs page.</p>
        </div>
        <div class="policyItem">
            <h3>Cookies and Sessions</h3>
            <p>We use a single server-side session cookie to keep you logged in. This cookie
            contains only a session identifier — no personal data. It expires when you close
            your browser or log out. We use no third-party tracking cookies, analytics pixels,
            or advertising scripts of any kind.</p>
        </div>
        <div class="policyItem">
            <h3>Data Retention</h3>
            <p>Your account and associated files remain stored until you delete them or request
            account deletion. To request deletion of all your data, contact us directly.
            We will process your request within 30 days of verification.</p>
        </div>
        <div class="policyItem">
            <h3>Security</h3>
            <p>Files are accessible only through unique, randomly generated UUIDs embedded in
            QR codes. We recommend treating your QR link as a private URL. Snap2See does not
            currently encrypt files at rest — please do not upload files containing sensitive
            personal, financial, or confidential information.</p>
        </div>
        <div class="policyItem">
            <h3>Changes to This Policy</h3>
            <p>If we make material changes to this policy we will update the date shown above.
            Continued use of the service after changes are posted constitutes your acceptance
            of the updated policy.</p>
        </div>
    </div>
</div>

<footer>
    <div style="margin-bottom:10px;font-size:15px;font-weight:700;letter-spacing:-.03em;">
        Snap<span style="color:var(--ac);">2See</span>
    </div>
    <div style="display:flex;gap:20px;justify-content:center;margin-bottom:12px;">
        <a href="#why">Why we built this</a>
        <a href="#privacy">Privacy Policy</a>
        <a href="/login">Sign In</a>
    </div>
    <div>2025 Snap2See. All rights reserved.</div>
</footer>
"""
    return page("Smart QR Platform", body, navbar=False)


# ── LOGIN ─────────────────────────────────────────────────────────────────────
@app.route("/login", methods=["GET", "POST"])
def login():
    error = ""
    if request.method == "POST":
        u = request.form.get("username", "").strip()
        p = request.form.get("password", "")
        if not u or not p:
            error = "Please enter a username and password."
        else:
            c.execute("SELECT id, password FROM users WHERE username=?", (u,))
            row = c.fetchone()
            if not row:
                c.execute("INSERT INTO users (username, password) VALUES (?,?)", (u, p))
                conn.commit()
                c.execute("SELECT id FROM users WHERE username=?", (u,))
                session["user_id"] = c.fetchone()[0]
                return redirect("/dashboard")
            elif row[1] != p:
                error = "Incorrect password."
            else:
                session["user_id"] = row[0]
                return redirect("/dashboard")

    err_html = (f'<p style="color:var(--red);font-size:13px;margin-bottom:12px;'
                f'padding:10px 14px;background:rgba(255,69,58,0.08);'
                f'border:1px solid rgba(255,69,58,0.18);border-radius:var(--rsm);">'
                f'{error}</p>') if error else ""

    body = f"""
<style>
.loginOuter{{min-height:100vh;display:flex;align-items:center;
    justify-content:center;padding:40px 24px;}}
.loginCard{{width:100%;max-width:400px;border-radius:var(--rxl);padding:40px 36px;}}
</style>
<div class="loginOuter">
    <div class="loginCard glassmd a0">
        <div style="text-align:center;margin-bottom:32px;">
            <svg width="42" height="42" viewBox="0 0 54 54" fill="none"
                style="margin:0 auto 14px;display:block;">
                <rect x="4"  y="4"  width="18" height="18" rx="3" stroke="#2997ff" stroke-width="2.5"/>
                <rect x="32" y="4"  width="18" height="18" rx="3" stroke="#2997ff" stroke-width="2.5"/>
                <rect x="4"  y="32" width="18" height="18" rx="3" stroke="#2997ff" stroke-width="2.5"/>
                <rect x="8"  y="8"  width="10" height="10" rx="1.5" fill="#2997ff"/>
                <rect x="36" y="8"  width="10" height="10" rx="1.5" fill="#2997ff"/>
                <rect x="8"  y="36" width="10" height="10" rx="1.5" fill="#2997ff"/>
                <rect x="32" y="32" width="5"  height="5"  rx="1" fill="#2997ff"/>
                <rect x="41" y="32" width="9"  height="5"  rx="1" fill="rgba(41,151,255,.5)"/>
                <rect x="32" y="41" width="18" height="5"  rx="1" fill="rgba(41,151,255,.5)"/>
            </svg>
            <h1 style="font-size:24px;font-weight:700;letter-spacing:-.03em;margin-bottom:6px;">
                Sign in to Snap2See
            </h1>
            <p style="font-size:14px;color:var(--t2);">
                New here? Signing in creates your account.
            </p>
        </div>

        {err_html}

        <form method="post" style="display:flex;flex-direction:column;gap:12px;">
            <input type="text"     name="username" placeholder="Username" required autofocus>
            <input type="password" name="password" placeholder="Password" required>
            <button type="submit" class="btn btnp"
                style="width:100%;padding:14px;margin-top:4px;border-radius:var(--rmd);">
                Continue
            </button>
        </form>

        <hr class="divider" style="margin:24px 0;">
        <div style="text-align:center;">
            <a href="/" style="font-size:13px;color:var(--t3);">Back to home</a>
        </div>
    </div>
</div>
"""
    return page("Sign In", body, navbar=False)


# ── DASHBOARD ────────────────────────────────────────────────────────────────
@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect("/login")

    c.execute("SELECT is_pro, username FROM users WHERE id=?", (session["user_id"],))
    row = c.fetchone()
    if not row:
        return redirect("/login")
    pro, username = row

    c.execute("SELECT COUNT(*) FROM files WHERE user_id=?", (session["user_id"],))
    qr_count = c.fetchone()[0]

    c.execute("SELECT COALESCE(SUM(scans),0) FROM files WHERE user_id=?", (session["user_id"],))
    total_scans = c.fetchone()[0]

    plan_badge = ('<span class="badge badgepro">Pro</span>' if pro
                  else '<span class="badge badgefree">Free</span>')
    plan_color = "var(--gold)" if pro else "var(--t2)"
    plan_label = "Pro" if pro else "Free"
    plan_sub   = "Unlimited QRs" if pro else "Upgrade for more"

    analytics_card = (
        '<a href="/manage" class="btn btng" style="padding:18px 20px;border-radius:var(--rlg);'
        'justify-content:flex-start;gap:14px;">'
        '<span style="display:flex;align-items:center;justify-content:center;width:36px;height:36px;'
        'border-radius:10px;background:rgba(41,151,255,0.1);flex-shrink:0;">'
        '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--ac)" '
        'stroke-width="2" stroke-linecap="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>'
        '</svg></span>'
        '<div style="text-align:left;"><div style="font-size:14px;font-weight:500;">Analytics</div>'
        '<div style="font-size:12px;color:var(--t2);">Scan statistics</div></div></a>'
        if pro else
        '<a href="/upgrade" class="btn" style="padding:18px 20px;border-radius:var(--rlg);'
        'justify-content:flex-start;gap:14px;background:rgba(255,214,10,0.06);'
        'border:1px solid rgba(255,214,10,0.18);">'
        '<span style="display:flex;align-items:center;justify-content:center;width:36px;height:36px;'
        'border-radius:10px;background:rgba(255,214,10,0.12);flex-shrink:0;">'
        '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--gold)" '
        'stroke-width="2" stroke-linecap="round">'
        '<polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>'
        '</svg></span>'
        '<div style="text-align:left;"><div style="font-size:14px;font-weight:500;color:var(--gold);">Upgrade to Pro</div>'
        '<div style="font-size:12px;color:var(--t2);">Unlock all features</div></div></a>'
    )

    body = f"""
<div class="pw">
    <div style="display:flex;align-items:flex-start;justify-content:space-between;
        margin-bottom:32px;" class="a0">
        <div>
            <p style="font-size:12px;color:var(--t3);margin-bottom:4px;
                text-transform:uppercase;letter-spacing:.06em;font-weight:500;">Dashboard</p>
            <h1 style="font-size:28px;font-weight:700;letter-spacing:-.04em;">
                Hello, {username}
            </h1>
        </div>
        {plan_badge}
    </div>

    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
        gap:12px;margin-bottom:28px;" class="a1">
        <div class="stat">
            <div class="statval">{qr_count}</div>
            <div class="statlbl">QR Codes</div>
        </div>
        <div class="stat">
            <div class="statval" style="color:var(--ac);">{total_scans}</div>
            <div class="statlbl">Total Scans</div>
        </div>
        <div class="stat">
            <div class="statval" style="color:{plan_color};font-size:28px;">{plan_label}</div>
            <div class="statlbl">{plan_sub}</div>
        </div>
    </div>

    <div class="glass a2" style="border-radius:var(--rxl);padding:32px;margin-bottom:20px;">
        <h2 style="font-size:18px;font-weight:600;letter-spacing:-.02em;margin-bottom:6px;">
            Create a QR Code
        </h2>
        <p style="font-size:14px;color:var(--t2);margin-bottom:24px;">
            Upload any file — image, PDF, video, or document — and receive a scannable
            QR code instantly. Images are watermarked automatically.
        </p>
        <form action="/upload" method="post" enctype="multipart/form-data">
            <input type="file" name="file" id="fi" required
                onchange="document.getElementById('fl').textContent=this.files[0].name;">
            <label for="fi" class="filedrop" id="fl">
                Click to choose a file, or drag and drop here
            </label>
            <button type="submit" class="btn btnp"
                style="width:100%;margin-top:14px;padding:14px;border-radius:var(--rmd);">
                Generate QR Code
            </button>
        </form>
    </div>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;" class="a3">
        <a href="/manage" class="btn btng"
            style="padding:18px 20px;border-radius:var(--rlg);justify-content:flex-start;gap:14px;">
            <span style="display:flex;align-items:center;justify-content:center;
                width:36px;height:36px;border-radius:10px;
                background:rgba(255,255,255,0.06);flex-shrink:0;">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
                    stroke="currentColor" stroke-width="2" stroke-linecap="round">
                    <rect x="3" y="3" width="7" height="7" rx="1"/>
                    <rect x="14" y="3" width="7" height="7" rx="1"/>
                    <rect x="3" y="14" width="7" height="7" rx="1"/>
                    <rect x="14" y="14" width="7" height="7" rx="1"/>
                </svg>
            </span>
            <div style="text-align:left;">
                <div style="font-size:14px;font-weight:500;">My QR Codes</div>
                <div style="font-size:12px;color:var(--t2);">View and manage</div>
            </div>
        </a>
        {analytics_card}
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
.feat{display:flex;align-items:center;gap:10px;padding:11px 0;
    border-bottom:1px solid var(--gb);font-size:14px;color:var(--t2);}
.feat:last-child{border-bottom:none;}
.fcheck{width:20px;height:20px;border-radius:50%;background:rgba(50,215,75,0.15);
    border:1px solid rgba(50,215,75,0.25);display:flex;align-items:center;
    justify-content:center;flex-shrink:0;}
</style>
<div class="pw" style="max-width:520px;">
    <div style="text-align:center;margin-bottom:40px;" class="a0">
        <div style="display:inline-flex;align-items:center;justify-content:center;
            width:52px;height:52px;border-radius:16px;
            background:rgba(255,214,10,0.1);border:1px solid rgba(255,214,10,0.2);
            margin-bottom:18px;">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none"
                stroke="var(--gold)" stroke-width="2" stroke-linecap="round">
                <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
            </svg>
        </div>
        <h1 style="font-size:30px;font-weight:700;letter-spacing:-.04em;margin-bottom:10px;">
            Snap2See Pro
        </h1>
        <p style="color:var(--t2);font-size:16px;">
            Everything you need for powerful QR campaigns.
        </p>
    </div>

    <div class="glass a1" style="border-radius:var(--rxl);padding:32px;
        border:1px solid rgba(255,214,10,0.2);position:relative;overflow:hidden;">
        <div style="position:absolute;top:0;right:0;width:220px;height:220px;
            background:radial-gradient(circle at top right,rgba(255,214,10,0.07),transparent 65%);
            pointer-events:none;"></div>

        <div style="display:flex;justify-content:space-between;align-items:flex-start;
            margin-bottom:28px;">
            <div>
                <div style="font-size:11px;font-weight:600;text-transform:uppercase;
                    letter-spacing:.08em;color:var(--gold);margin-bottom:8px;">Pro Plan</div>
                <div style="font-size:42px;font-weight:700;letter-spacing:-.05em;line-height:1;">
                    $10
                    <span style="font-size:17px;font-weight:400;color:var(--t2);">/ month</span>
                </div>
            </div>
            <span class="badge badgepro">Most Popular</span>
        </div>

        <div>
            <div class="feat"><div class="fcheck"><svg width="10" height="10" viewBox="0 0 12 12" fill="none" stroke="var(--green)" stroke-width="2.5" stroke-linecap="round"><polyline points="2 6 5 9 10 3"/></svg></div>Unlimited QR codes</div>
            <div class="feat"><div class="fcheck"><svg width="10" height="10" viewBox="0 0 12 12" fill="none" stroke="var(--green)" stroke-width="2.5" stroke-linecap="round"><polyline points="2 6 5 9 10 3"/></svg></div>Swap file content without reprinting</div>
            <div class="feat"><div class="fcheck"><svg width="10" height="10" viewBox="0 0 12 12" fill="none" stroke="var(--green)" stroke-width="2.5" stroke-linecap="round"><polyline points="2 6 5 9 10 3"/></svg></div>Advanced scan analytics</div>
            <div class="feat"><div class="fcheck"><svg width="10" height="10" viewBox="0 0 12 12" fill="none" stroke="var(--green)" stroke-width="2.5" stroke-linecap="round"><polyline points="2 6 5 9 10 3"/></svg></div>Custom watermark branding</div>
            <div class="feat"><div class="fcheck"><svg width="10" height="10" viewBox="0 0 12 12" fill="none" stroke="var(--green)" stroke-width="2.5" stroke-linecap="round"><polyline points="2 6 5 9 10 3"/></svg></div>Bulk QR generation</div>
            <div class="feat"><div class="fcheck"><svg width="10" height="10" viewBox="0 0 12 12" fill="none" stroke="var(--green)" stroke-width="2.5" stroke-linecap="round"><polyline points="2 6 5 9 10 3"/></svg></div>Priority support</div>
        </div>

        <form method="post" style="margin-top:28px;">
            <button type="submit" class="btn btngold"
                style="width:100%;padding:15px;font-size:16px;border-radius:var(--rmd);">
                Activate Pro — Demo
            </button>
        </form>
    </div>

    <div style="text-align:center;margin-top:20px;" class="a2">
        <a href="/dashboard" style="font-size:13px;color:var(--t3);">Back to dashboard</a>
    </div>
</div>
"""
    return page("Upgrade to Pro", body)


# ── UPLOAD ────────────────────────────────────────────────────────────────────
@app.route("/upload", methods=["POST"])
def upload():
    if "user_id" not in session:
        return redirect("/login")

    # 🔒 REQUIRE PRO
    c.execute("SELECT is_pro FROM users WHERE id=?", (session["user_id"],))
    user = c.fetchone()
    if not user or user[0] != 1:
        return redirect("/upgrade")  # force payment

    file = request.files.get("file")
    if not file or not file.filename:
        return redirect("/dashboard")

    file_id   = str(uuid.uuid4())
    safe      = file.filename.replace("/", "_").replace("..", "_")
    filename  = file_id + "_" + safe
    path      = os.path.join(UPLOADS, filename)
    file.save(path)

    watermarked = apply_watermark(path)

    c.execute("INSERT INTO files (id, user_id, filename, created) VALUES (?,?,?,?)",
              (file_id, session["user_id"], filename,
               datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()

    base    = request.host_url.rstrip("/")
    link    = f"{base}/view/{file_id}"
    qr_img  = qrcode.make(link)
    qr_path = os.path.join(QRS, file_id + ".png")
    qr_img.save(qr_path)

    return redirect(f"/qrview/{file_id}")  # 👈 NEW redirect

    file_id   = str(uuid.uuid4())
    safe      = file.filename.replace("/", "_").replace("..", "_")
    filename  = file_id + "_" + safe
    path      = os.path.join(UPLOADS, filename)
    file.save(path)

    watermarked = apply_watermark(path)

    c.execute("INSERT INTO files (id, user_id, filename, created) VALUES (?,?,?,?)",
              (file_id, session["user_id"], filename,
               datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()

    base    = request.host_url.rstrip("/")
    link    = f"{base}/view/{file_id}"
    qr_img  = qrcode.make(link)
    qr_path = os.path.join(QRS, file_id + ".png")
    qr_img.save(qr_path)

    wm_note = ""
    if watermarked:
        wm_note = """
        <div style="display:flex;align-items:center;gap:8px;padding:11px 15px;
            border-radius:var(--rsm);background:rgba(50,215,75,0.08);
            border:1px solid rgba(50,215,75,0.18);margin-bottom:20px;
            font-size:13px;color:var(--green);">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
                stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
                <polyline points="20 6 9 17 4 12"/>
            </svg>
            Watermark applied to your image
        </div>"""

    body = f"""
<div style="max-width:480px;margin:0 auto;padding:60px 24px;text-align:center;">
    <div style="display:inline-flex;align-items:center;justify-content:center;
        width:56px;height:56px;border-radius:50%;
        background:rgba(50,215,75,0.12);border:1px solid rgba(50,215,75,0.25);
        margin-bottom:20px;" class="a0">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none"
            stroke="var(--green)" stroke-width="2.5" stroke-linecap="round">
            <polyline points="20 6 9 17 4 12"/>
        </svg>
    </div>

    <h1 style="font-size:26px;font-weight:700;letter-spacing:-.03em;
        margin-bottom:8px;" class="a1">QR Code Created</h1>
    <p style="color:var(--t2);font-size:15px;margin-bottom:28px;" class="a2">
        Your QR code is live. Every scan is tracked in your dashboard.
    </p>

    {wm_note}

    <div class="glass a2" style="border-radius:var(--rxl);padding:28px;
        display:inline-block;margin-bottom:20px;">
        <img src="/qr/{file_id}" width="200" height="200"
            style="border-radius:10px;display:block;background:#fff;">
    </div>

    <div class="glass a3" style="border-radius:var(--rmd);padding:14px 18px;
        margin-bottom:28px;text-align:left;">
        <div style="font-size:11px;color:var(--t3);text-transform:uppercase;
            letter-spacing:.06em;margin-bottom:6px;">Scan URL</div>
        <div style="font-size:13px;color:var(--ac);word-break:break-all;">{link}</div>
    </div>

    <div style="display:flex;gap:10px;justify-content:center;flex-wrap:wrap;" class="a4">
        <a href="/dashboard" class="btn btnp">Back to Dashboard</a>
        <a href="/manage"    class="btn btng">View All QRs</a>
    </div>
</div>
"""
    return page("QR Created", body)

@app.route("/qrview/<id>")
def qrview(id):
    if "user_id" not in session:
        return redirect("/login")

    c.execute("SELECT filename, user_id FROM files WHERE id=?", (id,))
    row = c.fetchone()

    if not row or row[1] != session["user_id"]:
        return redirect("/manage")

    base = request.host_url.rstrip("/")
    link = f"{base}/view/{id}"

    body = f"""
    <div style="max-width:480px;margin:0 auto;padding:60px 24px;text-align:center;">
        <h1 style="font-size:26px;font-weight:700;margin-bottom:20px;">Your QR Code</h1>

        <div class="glass" style="padding:30px;border-radius:20px;margin-bottom:20px;">
            <img src="/qr/{id}" width="220" style="background:#fff;border-radius:10px;">
        </div>

        <div class="glass" style="padding:14px;border-radius:12px;margin-bottom:20px;">
            <div style="font-size:12px;color:gray;">Link</div>
            <div style="font-size:13px;color:#2997ff;word-break:break-all;">{link}</div>
        </div>

        <div style="display:flex;gap:10px;justify-content:center;">
            <a href="/dashboard" class="btn btnp">Dashboard</a>
            <a href="/manage" class="btn btng">All QRs</a>
        </div>
    </div>
    """
    return page("View QR", body)


# ── QR IMAGE ──────────────────────────────────────────────────────────────────
@app.route("/qr/<id>")
def qr_img(id):
    path = os.path.join(QRS, id + ".png")
    if not os.path.exists(path):
        return "Not found", 404
    return send_file(path)


# ── VIEW (scan endpoint) ──────────────────────────────────────────────────────
@app.route("/view/<id>")
def view(id):
    c.execute("SELECT filename FROM files WHERE id=?", (id,))
    row = c.fetchone()
    if not row:
        return ("<html><body style='font-family:sans-serif;padding:40px;background:#000;color:#fff;'>"
                "<h2>QR code not found.</h2></body></html>"), 404
    c.execute("UPDATE files SET scans = scans + 1 WHERE id=?", (id,))
    conn.commit()
    return send_file(os.path.join(UPLOADS, row[0]))


# ── MANAGE ────────────────────────────────────────────────────────────────────
@app.route("/manage")
def manage():
    if "user_id" not in session:
        return redirect("/login")

    c.execute("""SELECT id, filename, scans, created FROM files
                 WHERE user_id=? ORDER BY created DESC""", (session["user_id"],))
    rows = c.fetchall()

    if not rows:
        cards_html = """
        <div class="glass" style="border-radius:var(--rxl);padding:64px 32px;text-align:center;">
            <div style="width:52px;height:52px;border-radius:16px;
                background:rgba(255,255,255,0.05);border:1px solid var(--gb);
                display:flex;align-items:center;justify-content:center;margin:0 auto 16px;">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none"
                    stroke="var(--t3)" stroke-width="1.5" stroke-linecap="round">
                    <rect x="3" y="3" width="7" height="7" rx="1"/>
                    <rect x="14" y="3" width="7" height="7" rx="1"/>
                    <rect x="3" y="14" width="7" height="7" rx="1"/>
                    <rect x="14" y="14" width="7" height="7" rx="1"/>
                </svg>
            </div>
            <p style="color:var(--t2);margin-bottom:20px;font-size:15px;">
                No QR codes yet.
            </p>
            <a href="/dashboard" class="btn btnp">Create your first QR code</a>
        </div>"""
    else:
        cards_html = '<div style="display:flex;flex-direction:column;gap:10px;">'
        for r in rows:
            orig = r[1].split("_", 1)[1] if "_" in r[1] else r[1]
            date = r[3][:10] if r[3] else "—"
            cards_html += f"""
            <div class="glass" style="border-radius:var(--rlg);padding:18px 22px;
                display:flex;align-items:center;gap:16px;">
                <img src="/qr/{r[0]}" width="56" height="56"
                    style="border-radius:8px;border:1px solid var(--gb);
                           flex-shrink:0;background:#fff;">
                <div style="flex:1;min-width:0;">
                    <div style="font-size:14px;font-weight:500;margin-bottom:3px;
                        overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
                        {orig}
                    </div>
                    <div style="font-size:12px;color:var(--t3);">Created {date}</div>
                </div>
                <div style="text-align:right;flex-shrink:0;margin-right:8px;">
                    <div style="font-size:24px;font-weight:700;
                        letter-spacing:-.03em;color:var(--ac);">{r[2]}</div>
                    <div style="font-size:11px;color:var(--t3);
                        text-transform:uppercase;letter-spacing:.04em;">scans</div>
                </div>
                <div style="display:flex;gap:8px;flex-shrink:0;">
                    <a href="/qrview/{r[0]}" class="btn btng btnsm">View QR</a>
                    <a href="/edit/{r[0]}" class="btn btng btnsm">Edit</a>
                </div>
            </div>"""
        cards_html += "</div>"

    body = f"""
<div class="pw">
    <div style="display:flex;align-items:center;justify-content:space-between;
        margin-bottom:32px;" class="a0">
        <div>
            <p style="font-size:12px;color:var(--t3);text-transform:uppercase;
                letter-spacing:.06em;font-weight:500;margin-bottom:4px;">Management</p>
            <h1 style="font-size:26px;font-weight:700;letter-spacing:-.04em;">My QR Codes</h1>
        </div>
        <a href="/dashboard" class="btn btnp btnsm">+ New QR</a>
    </div>
    <div class="a1">{cards_html}</div>
</div>
"""
    return page("My QRs", body)


# ── EDIT ─────────────────────────────────────────────────────────────────────
@app.route("/edit/<id>", methods=["GET", "POST"])
def edit(id):
    if "user_id" not in session:
        return redirect("/login")

    c.execute("SELECT filename, user_id FROM files WHERE id=?", (id,))
    row = c.fetchone()
    if not row or row[1] != session["user_id"]:
        return redirect("/manage")

    if request.method == "POST":
        file = request.files.get("file")
        if file and file.filename:
            path = os.path.join(UPLOADS, row[0])
            file.save(path)
            apply_watermark(path)
        return redirect("/manage")

    body = f"""
<div class="pw" style="max-width:480px;">
    <div class="glass a0" style="border-radius:var(--rxl);padding:40px;">
        <h1 style="font-size:22px;font-weight:700;letter-spacing:-.03em;margin-bottom:8px;">
            Replace File
        </h1>
        <p style="color:var(--t2);font-size:14px;margin-bottom:24px;">
            The QR code URL stays the same. Only the content it delivers changes.
            Images will be watermarked automatically.
        </p>

        <div style="border-radius:var(--rmd);padding:12px 14px;
            background:rgba(255,255,255,0.03);border:1px solid var(--gb);
            margin-bottom:20px;">
            <div style="font-size:11px;color:var(--t3);text-transform:uppercase;
                letter-spacing:.05em;margin-bottom:4px;">QR ID</div>
            <div style="font-size:12px;font-family:monospace;color:var(--t2);">{id}</div>
        </div>

        <form method="post" enctype="multipart/form-data">
            <input type="file" name="file" id="ef" required
                onchange="document.getElementById('el').textContent=this.files[0].name;">
            <label for="ef" class="filedrop" id="el">
                Click to choose replacement file
            </label>
            <button type="submit" class="btn btnp"
                style="width:100%;margin-top:14px;padding:14px;border-radius:var(--rmd);">
                Update Content
            </button>
        </form>

        <div style="text-align:center;margin-top:18px;">
            <a href="/manage" style="font-size:13px;color:var(--t3);">Cancel</a>
        </div>
    </div>
</div>
"""
    return page("Edit QR", body)


# ── RUN ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
