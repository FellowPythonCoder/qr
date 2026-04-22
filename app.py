from flask import Flask, request, redirect, session, send_file, url_for
import sqlite3, os, uuid, qrcode
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

app = Flask(__name__)
app.secret_key = "snap2see-secret-key-2024"

UPLOADS    = "uploads"
QRS        = "qrs"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

# Stripe — set your real keys here or via environment variables
STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY", "pk_test_YOUR_KEY_HERE")
STRIPE_SECRET_KEY      = os.environ.get("STRIPE_SECRET_KEY",      "sk_test_YOUR_KEY_HERE")
STRIPE_PRICE_ID        = os.environ.get("STRIPE_PRICE_ID",        "price_YOUR_PRICE_ID")  # $10/mo recurring

# Points milestones: points_needed -> prize label
MILESTONES = {
    100:  "One Month of Pro — Free",
    1000: "One Year of Pro — Free",
}

os.makedirs(UPLOADS, exist_ok=True)
os.makedirs(QRS,     exist_ok=True)

# ── DATABASE ──────────────────────────────────────────────────────────────────
conn = sqlite3.connect("app.db", check_same_thread=False)
c    = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS users (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    username   TEXT UNIQUE,
    password   TEXT,
    is_pro     INTEGER DEFAULT 0,
    points     INTEGER DEFAULT 0,
    stripe_id  TEXT
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

# Add columns if upgrading an older db
for col, definition in [("points", "INTEGER DEFAULT 0"), ("stripe_id", "TEXT")]:
    try:
        c.execute(f"ALTER TABLE users ADD COLUMN {col} {definition}")
        conn.commit()
    except Exception:
        pass


# ── WATERMARK ─────────────────────────────────────────────────────────────────
def apply_watermark(path, text="Snap2See"):
    ext = os.path.splitext(path)[1].lower()
    if ext not in IMAGE_EXTS:
        return False
    try:
        img   = Image.open(path).convert("RGBA")
        w, h  = img.size
        layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw  = ImageDraw.Draw(layer)
        fsize = max(14, min(w, h) // 18)
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


# ── POINTS HELPERS ────────────────────────────────────────────────────────────
def get_next_milestone(pts):
    for threshold, prize in sorted(MILESTONES.items()):
        if pts < threshold:
            return threshold, prize
    last = sorted(MILESTONES.keys())[-1]
    return None, None

def points_bar_html(pts):
    nxt, prize = get_next_milestone(pts)
    if nxt is None:
        return '<p style="font-size:13px;color:var(--gold);">All milestones reached — contact us to claim your prizes.</p>'
    pct   = min(100, int(pts / nxt * 100))
    prev  = 0
    for t in sorted(MILESTONES.keys()):
        if t <= pts:
            prev = t
    bar_pts = pts - prev
    bar_max = nxt - prev
    bar_pct = min(100, int(bar_pts / bar_max * 100)) if bar_max > 0 else 100
    return f"""
    <div style="margin-top:4px;">
        <div style="display:flex;justify-content:space-between;
            font-size:12px;color:var(--t3);margin-bottom:8px;">
            <span>{pts} points</span>
            <span>Next: {nxt} pts — {prize}</span>
        </div>
        <div style="height:6px;border-radius:99px;background:rgba(255,255,255,0.08);overflow:hidden;">
            <div style="height:100%;width:{bar_pct}%;border-radius:99px;
                background:linear-gradient(90deg,var(--ac),var(--gold));
                transition:width .4s ease;"></div>
        </div>
        <div style="font-size:11px;color:var(--t3);margin-top:6px;">
            {nxt - pts} more scans to unlock: {prize}
        </div>
    </div>"""


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
input[type=text],input[type=password],input[type=email],input[type=number]{
    width:100%;padding:13px 16px;background:rgba(255,255,255,0.05);
    border:1px solid var(--gb);border-radius:var(--rmd);
    color:var(--t);font-size:15px;font-family:inherit;outline:none;
    transition:border-color .18s,box-shadow .18s;
}
input[type=text]:focus,input[type=password]:focus,
input[type=email]:focus,input[type=number]:focus{
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
            <a href="/rewards"  class="btn btng btnsm">Rewards</a>
            <a href="/manage"   class="btn btng btnsm">My QRs</a>
            <a href="/upgrade"  class="btn btngold btnsm">Pro</a>
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
    0%{opacity:0;transform:scale(.72) translateY(30px);}
    65%{transform:scale(1.04) translateY(-4px);}
    100%{opacity:1;transform:scale(1) translateY(0);}
}
@keyframes ringOut{
    0%{transform:scale(1);opacity:.45;}
    100%{transform:scale(2.4);opacity:0;}
}
@keyframes drift{
    0%,100%{transform:translateY(0);}
    50%{transform:translateY(-10px);}
}
@keyframes shimmer{
    0%{background-position:0% center;}
    100%{background-position:200% center;}
}
@keyframes lineIn{
    from{width:0;opacity:0;}
    to{width:60px;opacity:1;}
}

/* ── Hero ── */
.hero{
    min-height:100vh;
    display:flex;flex-direction:column;
    align-items:center;justify-content:center;
    text-align:center;padding:80px 24px 100px;
}
.logoWrap{
    position:relative;width:120px;height:120px;
    margin:0 auto 48px;animation:drift 8s ease-in-out infinite;
}
.ring{
    position:absolute;inset:0;border-radius:50%;
    border:1.5px solid rgba(41,151,255,0.3);
    animation:ringOut 3s ease-out infinite;
}
.ring:nth-child(2){animation-delay:1s;}
.ring:nth-child(3){animation-delay:2s;}
.logoBox{
    position:relative;z-index:2;width:120px;height:120px;border-radius:28px;
    background:linear-gradient(150deg,#0d1b2e,#0a1525);
    border:1px solid rgba(41,151,255,0.22);
    box-shadow:0 28px 80px rgba(41,151,255,0.16),inset 0 1px 0 rgba(255,255,255,0.07);
    display:flex;align-items:center;justify-content:center;
    animation:logoReveal .85s cubic-bezier(.34,1.56,.64,1) both;
}
.heroEyebrow{
    font-size:11px;font-weight:600;letter-spacing:.14em;text-transform:uppercase;
    color:var(--ac);margin-bottom:20px;
    animation:fadeUp .5s .1s ease both;opacity:0;animation-fill-mode:forwards;
}
.heroTitle{
    font-size:clamp(46px,9vw,72px);font-weight:700;
    letter-spacing:-.055em;line-height:.95;margin-bottom:24px;
    background:linear-gradient(110deg,#e8e8ed 30%,#2997ff 55%,#e8e8ed 78%);
    background-size:200% auto;
    -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;
    animation:shimmer 5s linear infinite, fadeUp .55s .18s ease both;
    opacity:0;animation-fill-mode:forwards;
}
.heroSub{
    font-size:19px;color:var(--t2);max-width:500px;
    margin:0 auto 48px;line-height:1.65;
    animation:fadeUp .5s .3s ease both;opacity:0;animation-fill-mode:forwards;
}
.heroCta{
    display:flex;gap:12px;flex-wrap:wrap;justify-content:center;
    animation:fadeUp .5s .42s ease both;opacity:0;animation-fill-mode:forwards;
}
.heroCta a{padding:15px 36px;font-size:16px;border-radius:var(--rlg);}

/* ── Section rule ── */
.sRule{
    display:block;width:0;height:2px;background:var(--ac);
    border-radius:2px;margin-bottom:20px;
    animation:lineIn .6s .1s ease both;animation-fill-mode:forwards;
}

/* ── Feature strip ── */
.strip{
    border-top:1px solid var(--gb);border-bottom:1px solid var(--gb);
    padding:40px 24px;
    display:grid;
    grid-template-columns:repeat(auto-fit,minmax(180px,1fr));
    gap:0;
    max-width:900px;margin:0 auto;
}
.stripItem{
    padding:24px 28px;
    border-right:1px solid var(--gb);
}
.stripItem:last-child{border-right:none;}
.stripNum{
    font-size:36px;font-weight:700;letter-spacing:-.04em;
    color:var(--ac);margin-bottom:4px;
}
.stripLabel{font-size:13px;color:var(--t2);}

/* ── How it works ── */
.howWrap{max-width:820px;margin:0 auto;padding:80px 24px;}
.howLabel{font-size:11px;font-weight:600;letter-spacing:.12em;
    text-transform:uppercase;color:var(--ac);margin-bottom:16px;}
.howTitle{font-size:clamp(26px,4vw,36px);font-weight:700;
    letter-spacing:-.04em;margin-bottom:40px;line-height:1.2;}
.howGrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:20px;}
.howStep{border-radius:var(--rlg);padding:28px;background:var(--glass);border:1px solid var(--gb);}
.stepNum{
    font-size:11px;font-weight:700;letter-spacing:.08em;
    text-transform:uppercase;color:var(--ac);margin-bottom:14px;
}
.howStep h3{font-size:16px;font-weight:600;margin-bottom:8px;letter-spacing:-.01em;}
.howStep p{font-size:13px;color:var(--t2);line-height:1.65;}

/* ── Rewards section ── */
.rewardsWrap{
    background:var(--bg1);border-top:1px solid var(--gb);
    border-bottom:1px solid var(--gb);
}
.rewardsInner{max-width:820px;margin:0 auto;padding:80px 24px;}
.rewardGrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));
    gap:14px;margin-top:36px;}
.rewardCard{
    border-radius:var(--rlg);padding:24px;
    background:var(--glass);border:1px solid var(--gb);
    position:relative;overflow:hidden;
}
.rewardPts{
    font-size:28px;font-weight:700;letter-spacing:-.04em;
    color:var(--gold);margin-bottom:6px;
}
.rewardPtsLabel{font-size:11px;color:var(--t3);text-transform:uppercase;
    letter-spacing:.06em;margin-bottom:12px;}
.rewardName{font-size:13px;font-weight:500;color:var(--t);}
.rewardBar{
    position:absolute;bottom:0;left:0;right:0;height:2px;
    background:linear-gradient(90deg,var(--ac),var(--gold));
}

/* ── Why section ── */
.whyWrap{max-width:820px;margin:0 auto;padding:80px 24px;}
.whyBody{font-size:16px;color:var(--t2);line-height:1.8;max-width:640px;}
.whyBody+.whyBody{margin-top:16px;}
.whyGrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));
    gap:16px;margin-top:40px;}
.whyCard{border-radius:var(--rlg);padding:24px;background:var(--glass);border:1px solid var(--gb);}
.whyIcon{width:36px;height:36px;border-radius:10px;
    background:rgba(41,151,255,0.1);border:1px solid rgba(41,151,255,0.18);
    display:flex;align-items:center;justify-content:center;margin-bottom:14px;}
.whyCard h3{font-size:15px;font-weight:600;margin-bottom:6px;letter-spacing:-.01em;}
.whyCard p{font-size:13px;color:var(--t2);line-height:1.65;}

/* ── Privacy ── */
.policyWrap{background:var(--bg1);border-top:1px solid var(--gb);}
.policyBlock{max-width:760px;margin:0 auto;padding:72px 24px 80px;}
.policyBlock h2{font-size:28px;font-weight:700;letter-spacing:-.03em;margin-bottom:6px;}
.policyUpdated{font-size:12px;color:var(--t3);margin-bottom:36px;}
.policyItem{margin-bottom:28px;padding-bottom:28px;border-bottom:1px solid var(--gb);}
.policyItem:last-child{border-bottom:none;margin-bottom:0;padding-bottom:0;}
.policyItem h3{font-size:15px;font-weight:600;margin-bottom:8px;}
.policyItem p{font-size:14px;color:var(--t2);line-height:1.75;}

/* ── Footer ── */
footer{border-top:1px solid var(--gb);padding:28px 24px;text-align:center;
    font-size:12px;color:var(--t3);}
footer a{color:var(--t3);}
footer a:hover{color:var(--t2);}
.footLinks{display:flex;gap:24px;justify-content:center;
    flex-wrap:wrap;margin:12px 0;}
</style>

<!-- HERO -->
<section class="hero">
    <div class="logoWrap">
        <div class="ring"></div>
        <div class="ring"></div>
        <div class="ring"></div>
        <div class="logoBox">
            <svg width="52" height="52" viewBox="0 0 54 54" fill="none">
                <rect x="4"  y="4"  width="18" height="18" rx="3" stroke="#2997ff" stroke-width="2.4"/>
                <rect x="32" y="4"  width="18" height="18" rx="3" stroke="#2997ff" stroke-width="2.4"/>
                <rect x="4"  y="32" width="18" height="18" rx="3" stroke="#2997ff" stroke-width="2.4"/>
                <rect x="8"  y="8"  width="10" height="10" rx="1.5" fill="#2997ff"/>
                <rect x="36" y="8"  width="10" height="10" rx="1.5" fill="#2997ff"/>
                <rect x="8"  y="36" width="10" height="10" rx="1.5" fill="#2997ff"/>
                <rect x="32" y="32" width="5"  height="5"  rx="1" fill="#2997ff"/>
                <rect x="41" y="32" width="9"  height="5"  rx="1" fill="rgba(41,151,255,.5)"/>
                <rect x="32" y="41" width="18" height="5"  rx="1" fill="rgba(41,151,255,.5)"/>
            </svg>
        </div>
    </div>

    <p class="heroEyebrow">Smart QR Infrastructure</p>
    <h1 class="heroTitle">Snap2See</h1>
    <p class="heroSub">
        Print once. Update forever. Every scan earns you points
        toward free Pro — one month at 100, one year at 1,000.
    </p>
    <div class="heroCta">
        <a href="/login" class="btn btnp">Create an Account</a>
        <a href="#how"   class="btn btng">See How It Works</a>
    </div>
</section>

<!-- STRIP STATS -->
<div style="border-top:1px solid var(--gb);">
<div class="strip">
    <div class="stripItem">
        <div class="stripNum">1 pt</div>
        <div class="stripLabel">earned per scan on your QRs</div>
    </div>
    <div class="stripItem">
        <div class="stripNum">100 pts</div>
        <div class="stripLabel">unlocks one free month of Pro</div>
    </div>
    <div class="stripItem">
        <div class="stripNum">Dynamic</div>
        <div class="stripLabel">update content, keep the same QR</div>
    </div>
    <div class="stripItem" style="border-right:none;">
        <div class="stripNum">Auto</div>
        <div class="stripLabel">watermark on every image upload</div>
    </div>
</div>
</div>

<!-- HOW IT WORKS -->
<div id="how" style="border-top:1px solid var(--gb);">
<div class="howWrap">
    <div class="howLabel">The Process</div>
    <h2 class="howTitle">Three steps from upload to live QR</h2>
    <div class="howGrid">
        <div class="howStep">
            <div class="stepNum">Step 01</div>
            <h3>Upload your file</h3>
            <p>Drop in any image, PDF, video, or document. We store it securely and watermark images automatically.</p>
        </div>
        <div class="howStep">
            <div class="stepNum">Step 02</div>
            <h3>Get your QR code</h3>
            <p>A unique QR is generated instantly. Print it, share it, stick it anywhere — the link never expires.</p>
        </div>
        <div class="howStep">
            <div class="stepNum">Step 03</div>
            <h3>Earn points per scan</h3>
            <p>Every time someone scans your QR, you earn one point. Rack them up and redeem for real rewards.</p>
        </div>
        <div class="howStep">
            <div class="stepNum">Step 04</div>
            <h3>Swap content anytime</h3>
            <p>The printed QR never changes. The file it delivers can be replaced in seconds from your dashboard.</p>
        </div>
    </div>
</div>
</div>

<!-- REWARDS -->
<div class="rewardsWrap" id="rewards">
<div class="rewardsInner">
    <div class="howLabel">Scan Rewards</div>
    <h2 class="howTitle" style="margin-bottom:10px;">Points that mean something</h2>
    <p style="font-size:15px;color:var(--t2);max-width:520px;line-height:1.7;margin-bottom:0;">
        Every scan of any QR code you own adds one point to your account.
        Hit a milestone and we reach out to arrange your prize.
        No catch, no fine print.
    </p>
    <div class="rewardGrid">
        <div class="rewardCard">
            <div class="rewardPts">100</div>
            <div class="rewardPtsLabel">points</div>
            <div class="rewardName">One Month of Pro — Free</div>
            <div class="rewardBar"></div>
        </div>
        <div class="rewardCard">
            <div class="rewardPts">1,000</div>
            <div class="rewardPtsLabel">points</div>
            <div class="rewardName">One Year of Pro — Free</div>
            <div class="rewardBar"></div>
        </div>
    </div>
</div>
</div>

<!-- WHY WE BUILT THIS -->
<div style="border-top:1px solid var(--gb);" id="why">
<div class="whyWrap">
    <div class="howLabel">Our Story</div>
    <h2 class="howTitle" style="margin-bottom:24px;">Why we built Snap2See</h2>
    <p class="whyBody">
        The problem was simple: you print flyers, cards, menus — and then something changes.
        A new menu item. A new portfolio piece. A different event link. Suddenly every QR code
        you printed is dead, and reprinting costs money you did not budget for.
    </p>
    <p class="whyBody">
        Snap2See separates the QR code from the content it points to. The code is permanent.
        The content is not. You swap the file from your dashboard and every printed QR in the
        world instantly serves the new version — no reprint, no downtime.
    </p>
    <p class="whyBody" style="margin-top:16px;">
        The rewards system came from watching creators share their QR codes and get nothing back
        for the effort of growing an audience. Scans are engagement. Engagement should have value.
        So we built a points system that turns every scan into something tangible.
    </p>
    <div class="whyGrid" style="margin-top:40px;">
        <div class="whyCard">
            <div class="whyIcon">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
                    stroke="#2997ff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/>
                    <polyline points="17 8 12 3 7 8"/>
                    <line x1="12" y1="3" x2="12" y2="15"/>
                </svg>
            </div>
            <h3>Permanent QR, live content</h3>
            <p>Print once and never touch the physical code again. Change the file behind it whenever you need to.</p>
        </div>
        <div class="whyCard">
            <div class="whyIcon">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
                    stroke="#2997ff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
                </svg>
            </div>
            <h3>Creator attribution built in</h3>
            <p>Images are watermarked the moment they are uploaded. Your name travels with your work, automatically.</p>
        </div>
        <div class="whyCard">
            <div class="whyIcon">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
                    stroke="#2997ff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <circle cx="12" cy="8" r="6"/>
                    <path d="M15.477 12.89L17 22l-5-3-5 3 1.523-9.11"/>
                </svg>
            </div>
            <h3>Scans become rewards</h3>
            <p>Every time your QR is scanned you earn a point. Points unlock real prizes at real milestones.</p>
        </div>
        <div class="whyCard">
            <div class="whyIcon">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
                    stroke="#2997ff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="3" y="11" width="18" height="11" rx="2"/>
                    <path d="M7 11V7a5 5 0 0110 0v4"/>
                </svg>
            </div>
            <h3>Private by default</h3>
            <p>Your files sit behind randomly generated UUIDs. Nothing is publicly listed or indexed.</p>
        </div>
    </div>
</div>
</div>

<!-- PRIVACY POLICY -->
<div class="policyWrap" id="privacy">
    <div class="policyBlock">
        <div class="howLabel">Legal</div>
        <h2>Privacy Policy</h2>
        <p class="policyUpdated">Last updated: January 2025</p>
        <div class="policyItem">
            <h3>Information We Collect</h3>
            <p>We collect the username and password you provide at registration, files you upload
            to generate QR codes, and a scan count per QR code. Scan counts are aggregate numbers
            only — we do not log identifying information about the people who scan your codes.
            We do not collect email addresses unless you provide one voluntarily.</p>
        </div>
        <div class="policyItem">
            <h3>How We Use Your Data</h3>
            <p>Files are stored solely to serve them when a QR code is scanned. Scan counts
            drive the points system and your dashboard analytics. We do not sell, rent, or share
            any of your data with third parties for advertising purposes.</p>
        </div>
        <div class="policyItem">
            <h3>Payments</h3>
            <p>Pro subscriptions are processed through Stripe. We never see or store your card
            details. Stripe's privacy policy governs all payment data. Your subscription status
            is stored as a flag in our database only.</p>
        </div>
        <div class="policyItem">
            <h3>File Storage and Watermarking</h3>
            <p>Files are stored on the server running this application. Images are watermarked
            with "Snap2See" on upload to protect creator attribution. You retain ownership of
            all files you upload and may delete them at any time from the Manage QRs page.</p>
        </div>
        <div class="policyItem">
            <h3>Cookies and Sessions</h3>
            <p>We use a single session cookie to keep you logged in. It contains only a session
            identifier — no personal data. We use no third-party tracking, analytics pixels,
            or advertising scripts.</p>
        </div>
        <div class="policyItem">
            <h3>Data Retention</h3>
            <p>Your account and files remain stored until you delete them or request account
            removal. Contact us directly for deletion requests; we process them within 30 days.</p>
        </div>
        <div class="policyItem">
            <h3>Security</h3>
            <p>Files are accessible only through randomly generated UUID links. Do not upload
            files containing sensitive personal, financial, or confidential information as we
            do not currently encrypt files at rest.</p>
        </div>
    </div>
</div>

<footer>
    <div style="font-size:16px;font-weight:700;letter-spacing:-.04em;margin-bottom:4px;">
        Snap<span style="color:var(--ac);">2See</span>
    </div>
    <div class="footLinks">
        <a href="#how">How It Works</a>
        <a href="#rewards">Rewards</a>
        <a href="#why">Our Story</a>
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

    err_html = (
        f'<p style="color:var(--red);font-size:13px;margin-bottom:12px;padding:10px 14px;'
        f'background:rgba(255,69,58,0.08);border:1px solid rgba(255,69,58,0.18);'
        f'border-radius:var(--rsm);">{error}</p>'
    ) if error else ""

    body = f"""
<style>
.lo{{min-height:100vh;display:flex;align-items:center;justify-content:center;padding:40px 24px;}}
.lc{{width:100%;max-width:400px;border-radius:var(--rxl);padding:40px 36px;}}
</style>
<div class="lo">
    <div class="lc glassmd a0">
        <div style="text-align:center;margin-bottom:32px;">
            <svg width="40" height="40" viewBox="0 0 54 54" fill="none"
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
            <h1 style="font-size:22px;font-weight:700;letter-spacing:-.03em;margin-bottom:6px;">
                Sign in to Snap2See
            </h1>
            <p style="font-size:14px;color:var(--t2);">New? Signing in creates your account.</p>
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
        <hr class="divider" style="margin:22px 0;">
        <div style="text-align:center;">
            <a href="/" style="font-size:13px;color:var(--t3);">Back to home</a>
        </div>
    </div>
</div>
"""
    return page("Sign In", body, navbar=False)


# ── LOGOUT ────────────────────────────────────────────────────────────────────
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


# ── DASHBOARD ────────────────────────────────────────────────────────────────
@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect("/login")
    c.execute("SELECT is_pro, username, points FROM users WHERE id=?", (session["user_id"],))
    row = c.fetchone()
    if not row:
        return redirect("/login")
    pro, username, pts = row[0], row[1], row[2] or 0

    c.execute("SELECT COUNT(*) FROM files WHERE user_id=?", (session["user_id"],))
    qr_count = c.fetchone()[0]
    c.execute("SELECT COALESCE(SUM(scans),0) FROM files WHERE user_id=?", (session["user_id"],))
    total_scans = c.fetchone()[0]

    plan_badge  = '<span class="badge badgepro">Pro</span>' if pro else '<span class="badge badgefree">Free</span>'
    plan_color  = "var(--gold)" if pro else "var(--t2)"
    plan_label  = "Pro" if pro else "Free"
    plan_sub    = "Unlimited QRs" if pro else "Upgrade for more"
    bar_html    = points_bar_html(pts)

    body = f"""
<div class="pw">
    <div style="display:flex;align-items:flex-start;justify-content:space-between;
        margin-bottom:32px;" class="a0">
        <div>
            <p style="font-size:12px;color:var(--t3);margin-bottom:4px;
                text-transform:uppercase;letter-spacing:.06em;font-weight:500;">Dashboard</p>
            <h1 style="font-size:28px;font-weight:700;letter-spacing:-.04em;">Hello, {username}</h1>
        </div>
        <div style="display:flex;gap:8px;align-items:center;">
            {plan_badge}
            <a href="/logout" class="btn btng btnsm">Sign Out</a>
        </div>
    </div>

    <!-- Stats -->
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
        gap:12px;margin-bottom:20px;" class="a1">
        <div class="stat">
            <div class="statval">{qr_count}</div>
            <div class="statlbl">QR Codes</div>
        </div>
        <div class="stat">
            <div class="statval" style="color:var(--ac);">{total_scans}</div>
            <div class="statlbl">Total Scans</div>
        </div>
        <div class="stat">
            <div class="statval" style="color:var(--gold);">{pts}</div>
            <div class="statlbl">Points</div>
        </div>
        <div class="stat">
            <div class="statval" style="color:{plan_color};font-size:26px;">{plan_label}</div>
            <div class="statlbl">{plan_sub}</div>
        </div>
    </div>

    <!-- Points bar -->
    <div class="glass a2" style="border-radius:var(--rlg);padding:20px 24px;margin-bottom:20px;">
        <div style="font-size:13px;font-weight:500;margin-bottom:10px;">Scan Rewards Progress</div>
        {bar_html}
        <div style="margin-top:12px;">
            <a href="/rewards" style="font-size:13px;color:var(--ac);">View all milestones</a>
        </div>
    </div>

    <!-- Upload -->
    <div class="glass a2" style="border-radius:var(--rxl);padding:32px;margin-bottom:20px;">
        <h2 style="font-size:18px;font-weight:600;letter-spacing:-.02em;margin-bottom:6px;">
            Create a QR Code
        </h2>
        <p style="font-size:14px;color:var(--t2);margin-bottom:24px;">
            Upload any file — image, PDF, video, or document. Images are watermarked automatically.
        </p>
        <form action="/upload" method="post" enctype="multipart/form-data">
            <input type="file" name="file" id="fi" required
                onchange="document.getElementById('fl').textContent=this.files[0].name;">
            <label for="fi" class="filedrop" id="fl">Click to choose a file</label>
            <button type="submit" class="btn btnp"
                style="width:100%;margin-top:14px;padding:14px;border-radius:var(--rmd);">
                Generate QR Code
            </button>
        </form>
    </div>

    <!-- Quick actions -->
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;" class="a3">
        <a href="/manage" class="btn btng"
            style="padding:18px 20px;border-radius:var(--rlg);justify-content:flex-start;gap:14px;">
            <span style="display:flex;align-items:center;justify-content:center;
                width:36px;height:36px;border-radius:10px;background:rgba(255,255,255,0.06);flex-shrink:0;">
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
        <a href="/rewards" class="btn btng"
            style="padding:18px 20px;border-radius:var(--rlg);justify-content:flex-start;gap:14px;">
            <span style="display:flex;align-items:center;justify-content:center;
                width:36px;height:36px;border-radius:10px;background:rgba(255,214,10,0.1);flex-shrink:0;">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
                    stroke="var(--gold)" stroke-width="2" stroke-linecap="round">
                    <circle cx="12" cy="8" r="6"/>
                    <path d="M15.477 12.89L17 22l-5-3-5 3 1.523-9.11"/>
                </svg>
            </span>
            <div style="text-align:left;">
                <div style="font-size:14px;font-weight:500;">My Rewards</div>
                <div style="font-size:12px;color:var(--t2);">{pts} points earned</div>
            </div>
        </a>
    </div>
</div>
"""
    return page("Dashboard", body)


# ── REWARDS PAGE ──────────────────────────────────────────────────────────────
@app.route("/rewards")
def rewards():
    if "user_id" not in session:
        return redirect("/login")
    c.execute("SELECT points, username FROM users WHERE id=?", (session["user_id"],))
    row = c.fetchone()
    pts, username = (row[0] or 0), row[1]

    milestone_html = ""
    for threshold, prize in sorted(MILESTONES.items()):
        unlocked = pts >= threshold
        pct      = min(100, int(pts / threshold * 100))
        color    = "var(--green)" if unlocked else "var(--t3)"
        bg       = "rgba(50,215,75,0.08)" if unlocked else "var(--glass)"
        border   = "rgba(50,215,75,0.2)" if unlocked else "var(--gb)"
        status   = "Unlocked" if unlocked else f"{threshold - pts} pts away"
        check    = """<div style="width:22px;height:22px;border-radius:50%;
            background:rgba(50,215,75,0.15);border:1px solid rgba(50,215,75,0.3);
            display:flex;align-items:center;justify-content:center;flex-shrink:0;">
            <svg width="10" height="10" viewBox="0 0 12 12" fill="none"
                stroke="var(--green)" stroke-width="2.5" stroke-linecap="round">
                <polyline points="2 6 5 9 10 3"/>
            </svg></div>""" if unlocked else f"""<div style="width:22px;height:22px;
            border-radius:50%;background:rgba(255,255,255,0.05);
            border:1px solid var(--gb);flex-shrink:0;"></div>"""

        milestone_html += f"""
        <div style="border-radius:var(--rlg);padding:20px 24px;
            background:{bg};border:1px solid {border};
            display:flex;align-items:center;gap:16px;margin-bottom:10px;">
            {check}
            <div style="flex:1;min-width:0;">
                <div style="font-size:15px;font-weight:500;margin-bottom:3px;">{prize}</div>
                <div style="height:4px;border-radius:99px;
                    background:rgba(255,255,255,0.07);overflow:hidden;margin-bottom:4px;">
                    <div style="height:100%;width:{pct}%;border-radius:99px;
                        background:{'var(--green)' if unlocked else 'linear-gradient(90deg,var(--ac),var(--gold))'};"></div>
                </div>
                <div style="font-size:12px;color:{color};">{status}</div>
            </div>
            <div style="text-align:right;flex-shrink:0;">
                <div style="font-size:22px;font-weight:700;
                    letter-spacing:-.03em;color:var(--gold);">{threshold}</div>
                <div style="font-size:11px;color:var(--t3);text-transform:uppercase;
                    letter-spacing:.04em;">pts</div>
            </div>
        </div>"""

    body = f"""
<div class="pw">
    <div class="a0" style="margin-bottom:32px;">
        <p style="font-size:12px;color:var(--t3);text-transform:uppercase;
            letter-spacing:.06em;font-weight:500;margin-bottom:4px;">Scan Rewards</p>
        <h1 style="font-size:26px;font-weight:700;letter-spacing:-.04em;margin-bottom:6px;">
            Your Points
        </h1>
        <p style="font-size:15px;color:var(--t2);">
            Every scan of your QR codes earns 1 point. Hit a milestone and we'll be in touch.
        </p>
    </div>

    <!-- Big points display -->
    <div class="glass a1" style="border-radius:var(--rxl);padding:32px;
        text-align:center;margin-bottom:28px;
        background:linear-gradient(135deg,rgba(255,214,10,0.05),rgba(41,151,255,0.05));">
        <div style="font-size:72px;font-weight:700;letter-spacing:-.05em;
            color:var(--gold);line-height:1;">{pts}</div>
        <div style="font-size:14px;color:var(--t2);margin-top:8px;margin-bottom:20px;">
            points earned, {username}
        </div>
        {points_bar_html(pts)}
    </div>

    <!-- Milestones -->
    <h2 style="font-size:17px;font-weight:600;letter-spacing:-.02em;
        margin-bottom:16px;" class="a2">All Milestones</h2>
    <div class="a2">{milestone_html}</div>

    <div class="glass a3" style="border-radius:var(--rlg);padding:18px 22px;
        margin-top:20px;font-size:13px;color:var(--t2);line-height:1.65;">
        When you reach a milestone, we will contact you using the username registered on your
        account. Make sure your username is something we can identify you by, or reach out to
        us directly after hitting a milestone to arrange your prize.
    </div>
</div>
"""
    return page("My Rewards", body)


# ── UPGRADE — Stripe ──────────────────────────────────────────────────────────
@app.route("/upgrade", methods=["GET", "POST"])
def upgrade():
    if "user_id" not in session:
        return redirect("/login")

    c.execute("SELECT is_pro FROM users WHERE id=?", (session["user_id"],))
    row = c.fetchone()
    already_pro = row and row[0] == 1

    stripe_key = STRIPE_PUBLISHABLE_KEY
    price_id   = STRIPE_PRICE_ID

    body = f"""
<style>
.feat{{display:flex;align-items:center;gap:10px;padding:11px 0;
    border-bottom:1px solid var(--gb);font-size:14px;color:var(--t2);}}
.feat:last-child{{border-bottom:none;}}
.fcheck{{width:20px;height:20px;border-radius:50%;background:rgba(50,215,75,0.15);
    border:1px solid rgba(50,215,75,0.25);display:flex;align-items:center;
    justify-content:center;flex-shrink:0;}}
#payment-form{{margin-top:24px;}}
#card-element{{
    padding:14px 16px;
    background:rgba(255,255,255,0.05);
    border:1px solid var(--gb);
    border-radius:var(--rmd);
    margin-bottom:14px;
}}
#card-errors{{color:var(--red);font-size:13px;margin-bottom:12px;}}
</style>

{"<div class='pw' style='max-width:520px;text-align:center;padding-top:80px;'><div class='glass' style='border-radius:var(--rxl);padding:40px;'><div style='font-size:48px;font-weight:700;color:var(--gold);margin-bottom:12px;'>Pro</div><p style='color:var(--t2);font-size:16px;margin-bottom:20px;'>You are already on the Pro plan.</p><a href=\"/dashboard\" class=\"btn btnp\">Back to Dashboard</a></div></div>"
  if already_pro else f'''
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
            Billed monthly at $10. Cancel any time.
        </p>
    </div>

    <div class="glass a1" style="border-radius:var(--rxl);padding:32px;
        border:1px solid rgba(255,214,10,0.2);position:relative;overflow:hidden;">
        <div style="position:absolute;top:0;right:0;width:220px;height:220px;
            background:radial-gradient(circle at top right,rgba(255,214,10,0.06),transparent 65%);
            pointer-events:none;"></div>

        <div style="display:flex;justify-content:space-between;align-items:flex-start;
            margin-bottom:28px;">
            <div>
                <div style="font-size:11px;font-weight:600;text-transform:uppercase;
                    letter-spacing:.08em;color:var(--gold);margin-bottom:8px;">Pro Plan</div>
                <div style="font-size:42px;font-weight:700;letter-spacing:-.05em;line-height:1;">
                    $10<span style="font-size:16px;font-weight:400;color:var(--t2);">/ mo</span>
                </div>
            </div>
            <span class="badge badgepro">Most Popular</span>
        </div>

        <div style="margin-bottom:28px;">
            <div class="feat"><div class="fcheck"><svg width="10" height="10" viewBox="0 0 12 12" fill="none" stroke="var(--green)" stroke-width="2.5" stroke-linecap="round"><polyline points="2 6 5 9 10 3"/></svg></div>Unlimited QR codes</div>
            <div class="feat"><div class="fcheck"><svg width="10" height="10" viewBox="0 0 12 12" fill="none" stroke="var(--green)" stroke-width="2.5" stroke-linecap="round"><polyline points="2 6 5 9 10 3"/></svg></div>Swap file content without reprinting</div>
            <div class="feat"><div class="fcheck"><svg width="10" height="10" viewBox="0 0 12 12" fill="none" stroke="var(--green)" stroke-width="2.5" stroke-linecap="round"><polyline points="2 6 5 9 10 3"/></svg></div>Advanced scan analytics</div>
            <div class="feat"><div class="fcheck"><svg width="10" height="10" viewBox="0 0 12 12" fill="none" stroke="var(--green)" stroke-width="2.5" stroke-linecap="round"><polyline points="2 6 5 9 10 3"/></svg></div>Custom watermark branding</div>
            <div class="feat"><div class="fcheck"><svg width="10" height="10" viewBox="0 0 12 12" fill="none" stroke="var(--green)" stroke-width="2.5" stroke-linecap="round"><polyline points="2 6 5 9 10 3"/></svg></div>Priority support</div>
        </div>

        <!-- Stripe Card Element -->
        <div id="card-errors"></div>
        <div id="card-element"></div>
        <button id="pay-btn" class="btn btngold" style="width:100%;padding:15px;font-size:16px;border-radius:var(--rmd);">
            Subscribe — $10 / month
        </button>

        <p style="font-size:12px;color:var(--t3);text-align:center;margin-top:14px;">
            Secured by Stripe. Cancel any time from your account.
        </p>
    </div>

    <div style="text-align:center;margin-top:20px;" class="a2">
        <a href="/dashboard" style="font-size:13px;color:var(--t3);">Back to dashboard</a>
    </div>
</div>

<script src="https://js.stripe.com/v3/"></script>
<script>
var stripe  = Stripe('{stripe_key}');
var elements = stripe.elements();
var style = {{
    base:{{
        color:'#f2f2f7',
        fontFamily:'-apple-system,BlinkMacSystemFont,SF Pro Text,sans-serif',
        fontSize:'15px',
        '::placeholder':{{color:'#58585f'}}
    }},
    invalid:{{color:'#ff453a'}}
}};
var card = elements.create('card', {{style:style}});
card.mount('#card-element');

card.on('change', function(e){{
    document.getElementById('card-errors').textContent = e.error ? e.error.message : '';
}});

document.getElementById('pay-btn').addEventListener('click', async function(){{
    this.disabled = true;
    this.textContent = 'Processing...';

    const resp = await fetch('/create-payment-intent', {{method:'POST'}});
    const data = await resp.json();

    if(data.error){{
        document.getElementById('card-errors').textContent = data.error;
        this.disabled = false;
        this.textContent = 'Subscribe — $10 / month';
        return;
    }}

    const result = await stripe.confirmCardPayment(data.clientSecret, {{
        payment_method:{{card:card}}
    }});

    if(result.error){{
        document.getElementById('card-errors').textContent = result.error.message;
        this.disabled = false;
        this.textContent = 'Subscribe — $10 / month';
    }} else if(result.paymentIntent.status === 'succeeded'){{
        window.location.href = '/payment-success';
    }}
}});
</script>
'''}
"""
    return page("Upgrade to Pro", body)


# ── STRIPE PAYMENT INTENT ────────────────────────────────────────────────────
@app.route("/create-payment-intent", methods=["POST"])
def create_payment_intent():
    if "user_id" not in session:
        from flask import jsonify
        return jsonify({"error": "Not logged in"}), 401
    try:
        import stripe as stripe_lib
        stripe_lib.api_key = STRIPE_SECRET_KEY
        intent = stripe_lib.PaymentIntent.create(
            amount=1000,          # $10.00 in cents
            currency="usd",
            automatic_payment_methods={"enabled": True},
            metadata={"user_id": str(session["user_id"])}
        )
        from flask import jsonify
        return jsonify({"clientSecret": intent.client_secret})
    except Exception as e:
        from flask import jsonify
        return jsonify({"error": str(e)}), 400


# ── PAYMENT SUCCESS ───────────────────────────────────────────────────────────
@app.route("/payment-success")
def payment_success():
    if "user_id" not in session:
        return redirect("/login")
    c.execute("UPDATE users SET is_pro=1 WHERE id=?", (session["user_id"],))
    conn.commit()
    body = """
<div style="max-width:460px;margin:0 auto;padding:80px 24px;text-align:center;">
    <div style="display:inline-flex;align-items:center;justify-content:center;
        width:60px;height:60px;border-radius:50%;
        background:rgba(50,215,75,0.12);border:1px solid rgba(50,215,75,0.25);
        margin-bottom:20px;" class="a0">
        <svg width="26" height="26" viewBox="0 0 24 24" fill="none"
            stroke="var(--green)" stroke-width="2.5" stroke-linecap="round">
            <polyline points="20 6 9 17 4 12"/>
        </svg>
    </div>
    <h1 style="font-size:26px;font-weight:700;letter-spacing:-.03em;
        margin-bottom:8px;color:var(--green);" class="a1">
        Welcome to Pro
    </h1>
    <p style="color:var(--t2);font-size:15px;margin-bottom:28px;" class="a2">
        Your account has been upgraded. All Pro features are now active.
    </p>
    <a href="/dashboard" class="btn btnp a3">Go to Dashboard</a>
</div>
"""
    return page("Payment Successful", body)


# ── UPLOAD ────────────────────────────────────────────────────────────────────
@app.route("/upload", methods=["POST"])
def upload():
    if "user_id" not in session:
        return redirect("/login")

    file = request.files.get("file")
    if not file or not file.filename:
        return redirect("/dashboard")

    file_id  = str(uuid.uuid4())
    safe     = file.filename.replace("/", "_").replace("..", "_")
    filename = file_id + "_" + safe
    path     = os.path.join(UPLOADS, filename)
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
        Your QR code is live. Every scan earns you 1 point.
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
        <a href="/dashboard" class="btn btnp">Dashboard</a>
        <a href="/manage"    class="btn btng">View All QRs</a>
    </div>
</div>
"""
    return page("QR Created", body)


# ── QR IMAGE ──────────────────────────────────────────────────────────────────
@app.route("/qr/<id>")
def qr_img(id):
    path = os.path.join(QRS, id + ".png")
    if not os.path.exists(path):
        return "Not found", 404
    return send_file(path)


# ── VIEW (scan — awards point to owner) ──────────────────────────────────────
@app.route("/view/<id>")
def view(id):
    c.execute("SELECT filename, user_id FROM files WHERE id=?", (id,))
    row = c.fetchone()
    if not row:
        return ("<html><body style='font-family:sans-serif;padding:40px;"
                "background:#000;color:#fff;'><h2>QR code not found.</h2>"
                "</body></html>"), 404
    filename, owner_id = row[0], row[1]

    # Increment scan count and award 1 point to the QR owner
    c.execute("UPDATE files SET scans = scans + 1 WHERE id=?", (id,))
    c.execute("UPDATE users SET points = COALESCE(points,0) + 1 WHERE id=?", (owner_id,))
    conn.commit()

    return send_file(os.path.join(UPLOADS, filename))


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
            <p style="color:var(--t2);margin-bottom:20px;font-size:15px;">No QR codes yet.</p>
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
                        overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{orig}</div>
                    <div style="font-size:12px;color:var(--t3);">Created {date}</div>
                </div>
                <div style="text-align:right;flex-shrink:0;margin-right:8px;">
                    <div style="font-size:22px;font-weight:700;
                        letter-spacing:-.03em;color:var(--ac);">{r[2]}</div>
                    <div style="font-size:11px;color:var(--t3);
                        text-transform:uppercase;letter-spacing:.04em;">scans</div>
                </div>
                <div style="display:flex;gap:8px;flex-shrink:0;">
                    <a href="/qrview/{r[0]}" class="btn btng btnsm">View QR</a>
                    <a href="/edit/{r[0]}"   class="btn btng btnsm">Edit</a>
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


# ── QR VIEW PAGE ──────────────────────────────────────────────────────────────
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
    orig = row[0].split("_", 1)[1] if "_" in row[0] else row[0]
    body = f"""
<div style="max-width:480px;margin:0 auto;padding:60px 24px;text-align:center;">
    <p style="font-size:12px;color:var(--t3);text-transform:uppercase;
        letter-spacing:.06em;margin-bottom:8px;">Your QR Code</p>
    <h1 style="font-size:22px;font-weight:700;letter-spacing:-.03em;margin-bottom:28px;" class="a0">
        {orig}
    </h1>
    <div class="glass a1" style="border-radius:var(--rxl);padding:28px;
        display:inline-block;margin-bottom:20px;">
        <img src="/qr/{id}" width="220" style="background:#fff;border-radius:10px;display:block;">
    </div>
    <div class="glass a2" style="border-radius:var(--rmd);padding:14px 18px;
        margin-bottom:24px;text-align:left;">
        <div style="font-size:11px;color:var(--t3);text-transform:uppercase;
            letter-spacing:.06em;margin-bottom:6px;">Scan URL</div>
        <div style="font-size:13px;color:var(--ac);word-break:break-all;">{link}</div>
    </div>
    <div style="display:flex;gap:10px;justify-content:center;" class="a3">
        <a href="/manage"   class="btn btnp">All QRs</a>
        <a href="/edit/{id}" class="btn btng">Replace File</a>
    </div>
</div>
"""
    return page("View QR", body)


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
            Images are watermarked automatically.
        </p>
        <div style="border-radius:var(--rmd);padding:12px 14px;
            background:rgba(255,255,255,0.03);border:1px solid var(--gb);margin-bottom:20px;">
            <div style="font-size:11px;color:var(--t3);text-transform:uppercase;
                letter-spacing:.05em;margin-bottom:4px;">QR ID</div>
            <div style="font-size:12px;font-family:monospace;color:var(--t2);">{id}</div>
        </div>
        <form method="post" enctype="multipart/form-data">
            <input type="file" name="file" id="ef" required
                onchange="document.getElementById('el').textContent=this.files[0].name;">
            <label for="ef" class="filedrop" id="el">Click to choose replacement file</label>
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
