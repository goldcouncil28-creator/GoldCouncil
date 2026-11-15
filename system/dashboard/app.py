"""داشبورد أدمن بوت التوصيات — تطبيق منفصل (FastAPI).

- المشتركون: من دفع، الحالة، الانتهاء — تفعيل/إيقاف/طرد/تمديد
- المدفوعات: تسجيل دفعة لكل مشترك (يدوي — كما في التصميم)
- الإشارات: طابور المراجعة (اعتماد/رفض) + السجل بالنتائج
- الإعدادات: وضع النشر (مراجعة/تلقائي) + رسالة الترحيب + المصادقة الثنائية

حماية:
- كلمة مرور في dashboard/.admin-password بصيغة هاش Argon2id
  (تُنشأ بـ dashboard/set_password.py من ملف نصي يُحذف بعدها؛
  هاش SHA256 قديم يُقبل كتوافق فقط). لو غير موجودة، الداشبورد
  مفتوح على localhost فقط مع تنبيه — عيّنها أولًا.
- حد محاولات الدخول: 5 محاولات فاشلة من نفس IP خلال 15 دقيقة = قفل.
- الجلسة تنتهي بعد 12 ساعة + زر خروج. المصادقة الثنائية TOTP اختيارية
  (تُفعّل من الإعدادات بعد أول دخول).
- سجل تدقيق (admin_audit): كل عملية إدارية من الويب أو تيليجرام +
  محاولات الدخول — يُعرض في صفحة «سجل العمليات».
"""
import hashlib
import hmac
import secrets
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pyotp
from argon2 import PasswordHasher
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

sys.path.insert(0, str(Path(__file__).parent.parent))

from telegram_bot.config import Config
from telegram_bot import review, store

DIR = Path(__file__).parent
PASS_FILE = DIR / ".admin-password"
TOTP_FILE = DIR / ".totp-secret"
JOURNAL_DB = Path(__file__).parent.parent / "data" / "journal.db"

SESSION_TTL_HOURS = 12
PREAUTH_TTL_MINUTES = 5
LOGIN_MAX_FAILS = 5
LOGIN_LOCK_MINUTES = 15

app = FastAPI(title="داشبورد بوت التوصيات")
SESSIONS: dict = {}   # token -> expiry (aware datetime)
PREAUTH: dict = {}    # pre-auth token -> expiry (بعد كلمة المرور، قبل TOTP)
PENDING_TOTP: dict = {}  # session token -> (secret, expiry) أثناء إعداد 2FA
_PH = PasswordHasher()


# ---------------------------------------------------------------- الحماية

def _client_ip(request: Request) -> str:
    try:
        return request.client.host or "?"
    except Exception:
        return "?"


def _audit_web(request: Request, action, target="", detail="", ok=1):
    """سجل تدقيق موحد مع تيليجرام (admin_chat_id=0 يعني الويب)."""
    try:
        ip = _client_ip(request)
        with store.conn() as c:
            c.execute("INSERT INTO admin_audit(ts, admin_chat_id, action, target, detail, ok) "
                      "VALUES(?,?,?,?,?,?)",
                      (datetime.now(timezone.utc).isoformat(), 0, f"web:{action}",
                       str(target), f"{ip} {detail}".strip(), int(ok)))
    except Exception:
        pass


def _pass_ok(pw: str) -> bool:
    if not PASS_FILE.exists():
        return False
    stored = PASS_FILE.read_text().strip()
    if stored.startswith("$argon2"):
        try:
            return _PH.verify(stored, pw)
        except Exception:
            return False
    # قديم: SHA256 (توافق فقط — الجديد Argon2id)
    return hmac.compare_digest(hashlib.sha256(pw.encode()).hexdigest(), stored)


def _login_allowed(ip: str) -> bool:
    try:
        with store.conn() as c:
            cutoff = (datetime.now(timezone.utc) - timedelta(minutes=LOGIN_LOCK_MINUTES)).isoformat()
            n = c.execute("SELECT COUNT(*) FROM login_attempts WHERE ip=? AND ok=0 AND ts>=?",
                          (ip, cutoff)).fetchone()[0]
            return n < LOGIN_MAX_FAILS
    except Exception:
        return True


def _record_login(ip: str, ok: bool):
    try:
        with store.conn() as c:
            c.execute("DELETE FROM login_attempts WHERE ts < ?",
                      ((datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),))
            c.execute("INSERT INTO login_attempts(ip, ts, ok) VALUES(?,?,?)",
                      (ip, datetime.now(timezone.utc).isoformat(), int(ok)))
    except Exception:
        pass


def _new_session() -> str:
    tok = secrets.token_hex(16)
    SESSIONS[tok] = datetime.now(timezone.utc) + timedelta(hours=SESSION_TTL_HOURS)
    return tok


def _set_session_cookie(resp, tok):
    resp.set_cookie("session", tok, httponly=True,
                    max_age=SESSION_TTL_HOURS * 3600, samesite="lax")


def _authed(request: Request) -> bool:
    if not PASS_FILE.exists():
        return True  # localhost فقط + تنبيه في الواجهة
    tok = request.cookies.get("session")
    exp = SESSIONS.get(tok)
    if exp is None:
        return False
    if exp <= datetime.now(timezone.utc):
        SESSIONS.pop(tok, None)
        return False
    return True


def _need_auth(request: Request):
    if not _authed(request):
        return RedirectResponse("/login")
    return None


def layout(title: str, body: str, warn: bool = False) -> str:
    banner = ("<div class='warn'>⚠️ لم تعيّن كلمة مرور بعد — ضعها في "
              "dashboard/.admin-password ثم أعد التشغيل</div>"
              if warn else "")
    return f"""<!DOCTYPE html><html lang="ar" dir="rtl"><head><meta charset="utf-8">
<title>{title}</title><style>
body{{background:#0e1117;color:#e0e0e0;font-family:sans-serif;margin:0;padding:20px}}
a{{color:#42a5f5}} nav a{{margin-left:16px}} table{{border-collapse:collapse;width:100%}}
th,td{{border:1px solid #333;padding:8px;text-align:right}} th{{background:#1a1f2b}}
button,.btn{{background:#1a6fb5;color:#fff;border:0;padding:6px 14px;border-radius:6px;cursor:pointer}}
input,select{{background:#1a1f2b;color:#e0e0e0;border:1px solid #333;padding:6px;border-radius:6px}}
.warn{{background:#5a3d00;padding:10px;border-radius:8px;margin-bottom:16px}}
.ok{{color:#4caf50}} .bad{{color:#ef5350}} .card{{background:#161b26;padding:16px;border-radius:10px;margin:10px 0}}
</style></head><body>
<nav><a href="/">الرئيسية</a><a href="/subscribers">المشتركون</a>
<a href="/payments">المدفوعات</a><a href="/signals">الإشارات</a>
<a href="/settings">الإعدادات</a><a href="/audit">سجل العمليات</a>
<a href="/logout">خروج</a></nav>
<h1>{title}</h1>{banner}{body}</body></html>"""


def _subscribers_with_payments():
    with store.conn() as c:
        subs = c.execute("SELECT chat_id, username, name, status, activated_at, "
                         "expires_at, invite_link FROM subscribers "
                         "ORDER BY status, expires_at").fetchall()
        pays = {}
        for row in c.execute("SELECT subscriber_chat_id, amount, currency, method, "
                             "paid_at FROM payments ORDER BY paid_at DESC").fetchall():
            pays.setdefault(row[0], row)
    return subs, pays


def _journal_stats():
    if not JOURNAL_DB.exists():
        return {"closed": 0, "wins": 0, "losses": 0, "win_rate": 0}
    import journal as _j  # noqa
    return _j.stats()


# ---------------------------------------------------------------- الدخول

@app.get("/login", response_class=HTMLResponse)
def login_page():
    return layout("دخول الأدمن", """
<form method="post" action="/login">
<input type="password" name="password" placeholder="كلمة المرور" required>
<button>دخول</button></form>""")


@app.post("/login")
def login(request: Request, password: str = Form(...)):
    ip = _client_ip(request)
    if not _login_allowed(ip):
        _audit_web(request, "login", detail="locked", ok=0)
        return HTMLResponse(layout("دخول الأدمن",
                                   "<p class='bad'>محاولات كثيرة — انتظر 15 دقيقة ثم جرّب مجددًا</p>"),
                            status_code=429)
    if _pass_ok(password):
        _record_login(ip, True)
        _audit_web(request, "login", ok=1)
        if TOTP_FILE.exists():
            pre = secrets.token_hex(16)
            PREAUTH[pre] = datetime.now(timezone.utc) + timedelta(minutes=PREAUTH_TTL_MINUTES)
            r = RedirectResponse("/login-2fa", status_code=303)
            r.set_cookie("preauth", pre, httponly=True, max_age=PREAUTH_TTL_MINUTES * 60)
            return r
        tok = _new_session()
        r = RedirectResponse("/", status_code=303)
        _set_session_cookie(r, tok)
        return r
    _record_login(ip, False)
    _audit_web(request, "login", ok=0)
    return HTMLResponse(layout("دخول الأدمن", "<p class='bad'>كلمة مرور خاطئة</p>"))


@app.get("/login-2fa", response_class=HTMLResponse)
def login_2fa_page(request: Request):
    pre = request.cookies.get("preauth")
    if not pre or pre not in PREAUTH or PREAUTH[pre] <= datetime.now(timezone.utc):
        return RedirectResponse("/login")
    return layout("تحقق بخطوتين", """
<form method="post" action="/login-2fa">
<input name="code" placeholder="كود 6 أرقام من تطبيق Authenticator" required inputmode="numeric">
<button>تحقق ودخول</button></form>""")


@app.post("/login-2fa")
def login_2fa(request: Request, code: str = Form(...)):
    ip = _client_ip(request)
    pre = request.cookies.get("preauth")
    if not pre or pre not in PREAUTH or PREAUTH[pre] <= datetime.now(timezone.utc):
        return RedirectResponse("/login")
    if not _login_allowed(ip):
        return HTMLResponse(layout("تحقق بخطوتين",
                                   "<p class='bad'>محاولات كثيرة — انتظر 15 دقيقة ثم جرّب مجددًا</p>"),
                            status_code=429)
    secret = TOTP_FILE.read_text().strip() if TOTP_FILE.exists() else ""
    ok = bool(secret) and pyotp.TOTP(secret).verify(code.strip(), valid_window=1)
    if not ok:
        _record_login(ip, False)
        _audit_web(request, "login-2fa", ok=0)
        return HTMLResponse(layout("تحقق بخطوتين", "<p class='bad'>كود غير صحيح</p>"))
    PREAUTH.pop(pre, None)
    _record_login(ip, True)
    _audit_web(request, "login-2fa", ok=1)
    tok = _new_session()
    r = RedirectResponse("/", status_code=303)
    _set_session_cookie(r, tok)
    r.delete_cookie("preauth")
    return r


@app.get("/logout")
def logout(request: Request):
    tok = request.cookies.get("session")
    if tok:
        SESSIONS.pop(tok, None)
    _audit_web(request, "logout", ok=1)
    r = RedirectResponse("/login", status_code=303)
    r.delete_cookie("session")
    return r


# ---------------------------------------------------------------- الصفحات

@app.get("/", response_class=HTMLResponse)
def overview(request: Request):
    redir = _need_auth(request)
    if redir:
        return redir
    cfg = Config.load()
    subs, pays = _subscribers_with_payments()
    active = sum(1 for s in subs if s[3] == "active")
    paid = sum(1 for s in subs if s[0] in pays)
    st = _journal_stats()
    with store.conn() as c:
        pend = c.execute("SELECT COUNT(*) FROM pending WHERE status='pending'").fetchone()[0]
    body = f"""
<div class="card">الوضع: <b>{cfg.mode}</b> | توصيات مراجَعة: {cfg.reviewed_count} |
بوت مهيّأ: {'✅' if cfg.configured else '❌ (ينقص توكن/قناة/أدمن)'}</div>
<div class="card">مشتركون نشطون: <b>{active}</b> | دفع منهم: <b>{paid}</b> |
بانتظار المراجعة: <b>{pend}</b></div>
<div class="card">سجل الإشارات: مغلقة {st['closed']} | رابحة {st['wins']} |
خاسرة {st['losses']} | نسبة فوز {st['win_rate']}%</div>"""
    return layout("داشبورد بوت التوصيات", body, warn=not PASS_FILE.exists())


@app.get("/subscribers", response_class=HTMLResponse)
def subscribers_page(request: Request):
    redir = _need_auth(request)
    if redir:
        return redir
    subs, pays = _subscribers_with_payments()
    rows = ""
    for chat_id, username, name, status, act, exp, _link in subs:
        p = pays.get(chat_id)
        pay_txt = (f"{p[1]} {p[2]} ({p[3] or ''}) {p[4][:10]}" if p else "<span class='bad'>لم يدفع</span>")
        rows += f"""<tr><td>{chat_id}</td><td>{name or ''} {('@'+username) if username else ''}</td>
<td>{status}</td><td>{exp[:10] if exp else '؟'}</td><td>{pay_txt}</td>
<td><form style="display:inline" method="post" action="/subscribers/{chat_id}/pause"><button>إيقاف</button></form>
<form style="display:inline" method="post" action="/subscribers/{chat_id}/kick"><button>طرد</button></form>
<form style="display:inline" method="post" action="/subscribers/{chat_id}/extend">
<input type="number" name="days" value="30" style="width:60px"><button>تمديد</button></form></td></tr>"""
    body = f"""
<form method="post" action="/subscribers/activate">
<input name="chat_id" placeholder="chat_id" required>
<input name="name" placeholder="الاسم">
<input type="number" name="days" value="30" required> يوم
<button>تفعيل مشترك</button></form>
<table><tr><th>chat_id</th><th>الاسم</th><th>الحالة</th><th>ينتهي</th><th>آخر دفعة</th><th>إجراءات</th></tr>
{rows}</table>"""
    return layout("المشتركون", body)


@app.post("/subscribers/activate")
def sub_activate(request: Request, chat_id: int = Form(...), name: str = Form(""),
                 days: int = Form(30)):
    redir = _need_auth(request)
    if redir:
        return redir
    cfg = Config.load()
    exp = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()
    link = None
    if cfg.configured:
        try:
            from telegram_bot.api import BotApi
            link = BotApi(cfg.token).create_invite_link(
                cfg.channel_id, name=f"sub-{chat_id}")["invite_link"]
        except Exception:
            pass
    with store.conn() as c:
        c.execute("INSERT INTO subscribers(chat_id, name, status, activated_at, expires_at, invite_link, warned) "
                  "VALUES(?,?, 'active', ?, ?, ?, 0) "
                  "ON CONFLICT(chat_id) DO UPDATE SET status='active', expires_at=excluded.expires_at, "
                  "invite_link=excluded.invite_link, warned=0",
                  (chat_id, name, datetime.now(timezone.utc).isoformat(), exp, link))
    _audit_web(request, "activate", chat_id, f"{days}d {name}")
    return RedirectResponse("/subscribers", status_code=303)


def _sub_action(request: Request, chat_id: int, status: str):
    redir = _need_auth(request)
    if redir:
        return redir
    cfg = Config.load()
    with store.conn() as c:
        row = c.execute("SELECT invite_link FROM subscribers WHERE chat_id=?", (chat_id,)).fetchone()
        c.execute("UPDATE subscribers SET status=? WHERE chat_id=?", (status, chat_id))
    if cfg.configured and status in ("paused", "kicked"):
        try:
            from telegram_bot.api import BotApi
            api = BotApi(cfg.token)
            api.ban(cfg.channel_id, chat_id)
            if row and row[0]:
                api.revoke_invite_link(cfg.channel_id, row[0])
        except Exception:
            pass
    _audit_web(request, f"sub:{status}", chat_id)
    return RedirectResponse("/subscribers", status_code=303)


@app.post("/subscribers/{chat_id}/pause")
def sub_pause(request: Request, chat_id: int):
    return _sub_action(request, chat_id, "paused")


@app.post("/subscribers/{chat_id}/kick")
def sub_kick(request: Request, chat_id: int):
    return _sub_action(request, chat_id, "kicked")


@app.post("/subscribers/{chat_id}/extend")
def sub_extend(request: Request, chat_id: int, days: int = Form(30)):
    redir = _need_auth(request)
    if redir:
        return redir
    with store.conn() as c:
        row = c.execute("SELECT expires_at FROM subscribers WHERE chat_id=?", (chat_id,)).fetchone()
        cur = row[0] if row and row[0] else datetime.now(timezone.utc).isoformat()
        try:
            base = datetime.fromisoformat(cur)
        except Exception:
            base = datetime.now(timezone.utc)
        if base.tzinfo is None:
            base = base.replace(tzinfo=timezone.utc)
        new_exp = max(base, datetime.now(timezone.utc)) + timedelta(days=days)
        c.execute("UPDATE subscribers SET status='active', expires_at=?, warned=0 WHERE chat_id=?",
                  (new_exp.isoformat(), chat_id))
    _audit_web(request, "extend", chat_id, f"{days}d")
    return RedirectResponse("/subscribers", status_code=303)


@app.get("/payments", response_class=HTMLResponse)
def payments_page(request: Request):
    redir = _need_auth(request)
    if redir:
        return redir
    with store.conn() as c:
        subs = c.execute("SELECT chat_id, name FROM subscribers ORDER BY name").fetchall()
        rows = c.execute("SELECT id, subscriber_chat_id, amount, currency, method, "
                         "period_days, paid_at, note FROM payments ORDER BY paid_at DESC").fetchall()
    opts = "".join(f"<option value='{i}'>{n or i}</option>" for i, n in subs)
    trs = "".join(f"<tr><td>{r[1]}</td><td>{r[2]} {r[3]}</td><td>{r[4] or ''}</td>"
                   f"<td>{r[5] or ''} يوم</td><td>{r[6][:10] if r[6] else ''}</td>"
                   f"<td>{r[7] or ''}</td></tr>" for r in rows)
    body = f"""
<form method="post" action="/payments">
<select name="subscriber_chat_id" required>{opts}</select>
<input type="number" step="0.01" name="amount" placeholder="المبلغ" required>
<input name="currency" value="USD" style="width:70px">
<input name="method" placeholder="طريقة الدفع (تحويل/كاش/USDT)">
<input type="number" name="period_days" value="30" style="width:80px"> يوم
<input name="note" placeholder="ملاحظة">
<button>تسجيل دفعة</button></form>
<table><tr><th>المشترك</th><th>المبلغ</th><th>الطريقة</th><th>المدة</th><th>التاريخ</th><th>ملاحظة</th></tr>
{trs}</table>"""
    return layout("المدفوعات — من دفع؟", body)


@app.post("/payments")
def payment_add(request: Request, subscriber_chat_id: int = Form(...),
                amount: float = Form(...), currency: str = Form("USD"),
                method: str = Form(""), period_days: int = Form(30),
                note: str = Form("")):
    redir = _need_auth(request)
    if redir:
        return redir
    with store.conn() as c:
        c.execute("INSERT INTO payments(subscriber_chat_id, amount, currency, method, "
                  "period_days, paid_at, note) VALUES(?,?,?,?,?,?,?)",
                  (subscriber_chat_id, amount, currency, method, period_days,
                   datetime.now(timezone.utc).isoformat(), note))
    _audit_web(request, "payment", subscriber_chat_id, f"{amount} {currency} {method}")
    return RedirectResponse("/payments", status_code=303)


@app.get("/signals", response_class=HTMLResponse)
def signals_page(request: Request):
    redir = _need_auth(request)
    if redir:
        return redir
    with store.conn() as c:
        pend = c.execute("SELECT signal_id, created_at FROM pending "
                         "WHERE status='pending' ORDER BY created_at").fetchall()
        pubs = c.execute("SELECT signal_id, channel_message_id, published_at FROM deliveries "
                         "ORDER BY published_at DESC LIMIT 20").fetchall()
    jrows = {}
    if JOURNAL_DB.exists():
        jc = sqlite3.connect(JOURNAL_DB)
        for r in jc.execute("SELECT id, symbol, direction, status, pnl_r FROM signals"):
            jrows[r[0]] = r
        jc.close()
    prows = "".join(
        f"<tr><td>#{i}</td><td>{t}</td><td>"
        f"<form style='display:inline' method='post' action='/signals/{i}/approve'><button>اعتماد</button></form> "
        f"<form style='display:inline' method='post' action='/signals/{i}/reject'><button>رفض</button></form></td></tr>"
        for i, t in pend)
    urows = ""
    for sid, _mid, pub in pubs:
        j = jrows.get(sid)
        urows += (f"<tr><td>#{sid}</td><td>{j[1] if j else ''} {j[2] if j else ''}</td>"
                  f"<td>{j[3] if j else ''} ({j[4] if j and j[4] is not None else ''}R)</td>"
                  f"<td>{pub[:16]}</td></tr>")
    body = f"""<h2>بانتظار المراجعة</h2><table><tr><th>التوصية</th><th>منذ</th><th>إجراء</th></tr>
{prows or '<tr><td colspan=3>لا شيء</td></tr>'}</table>
<h2>المنشورة</h2><table><tr><th>التوصية</th><th>الاتجاه</th><th>النتيجة</th><th>نُشرت</th></tr>
{urows or '<tr><td colspan=4>لا شيء</td></tr>'}</table>"""
    return layout("الإشارات", body)


@app.post("/signals/{signal_id}/approve")
def signal_approve(request: Request, signal_id: int):
    redir = _need_auth(request)
    if redir:
        return redir
    cfg = Config.load()
    if not cfg.configured:
        return HTMLResponse(layout("خطأ", "<p class='bad'>البوت غير مهيّأ (توكن/قناة/أدمن)</p>"))
    from telegram_bot.api import BotApi
    review.approve(BotApi(cfg.token), cfg, signal_id)
    _audit_web(request, "signal:approve", signal_id)
    return RedirectResponse("/signals", status_code=303)


@app.post("/signals/{signal_id}/reject")
def signal_reject(request: Request, signal_id: int):
    redir = _need_auth(request)
    if redir:
        return redir
    review.reject(Config.load(), signal_id)
    _audit_web(request, "signal:reject", signal_id)
    return RedirectResponse("/signals", status_code=303)


@app.get("/audit", response_class=HTMLResponse)
def audit_page(request: Request):
    redir = _need_auth(request)
    if redir:
        return redir
    with store.conn() as c:
        rows = c.execute("SELECT ts, admin_chat_id, action, target, detail, ok FROM admin_audit "
                         "ORDER BY id DESC LIMIT 100").fetchall()
    trs = "".join(
        f"<tr><td>{t[:16]}</td><td>{'ويب' if a == 0 else a}</td><td>{ac}</td>"
        f"<td>{tg}</td><td>{'✅' if ok else '⛔'}</td></tr>"
        for t, a, ac, tg, _d, ok in rows)
    body = ("<table><tr><th>الوقت</th><th>الفاعل</th><th>العملية</th>"
            "<th>الهدف</th><th>النتيجة</th></tr>"
            f"{trs or '<tr><td colspan=5>لا عمليات مسجلة</td></tr>'}</table>")
    return layout("سجل العمليات", body)


@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    redir = _need_auth(request)
    if redir:
        return redir
    cfg = Config.load()
    if TOTP_FILE.exists():
        twofa = ("<div class='card'>المصادقة الثنائية (TOTP): <b class='ok'>مفعّلة ✅</b>"
                 "<form method='post' action='/settings/2fa-disable'>"
                 "<input name='code' placeholder='كود حالي للإلغاء' required inputmode='numeric'>"
                 "<button>إلغاء التفعيل</button></form></div>")
    else:
        twofa = ("<div class='card'>المصادقة الثنائية (TOTP): <b>غير مفعّلة</b> — "
                 "<a href='/settings/2fa-setup'>تفعيلها</a> (تحتاج تطبيق Authenticator)</div>")
    body = f"""
<div class="card">الوضع الحالي: <b>{cfg.mode}</b> | مراجَعة: {cfg.reviewed_count} |
تلقائي بعد: {cfg.auto_after_reviewed}</div>
<form method="post" action="/settings/mode">
<select name="mode"><option value="review">مراجعة</option><option value="auto">تلقائي</option></select>
<button>تغيير الوضع</button></form>
<form method="post" action="/settings/welcome">
<input name="welcome" value="{cfg.welcome}" style="width:70%">
<button>حفظ رسالة الترحيب</button></form>
{twofa}
<p>التوكن: {'✅ موجود' if cfg.token else '❌ غير موجود'} |
القناة: {cfg.channel_id or '❌ غير محددة'} | الأدمن: {cfg.admin_ids or '❌'}</p>"""
    return layout("الإعدادات", body)


@app.post("/settings/mode")
def settings_mode(request: Request, mode: str = Form(...)):
    redir = _need_auth(request)
    if redir:
        return redir
    if mode in ("review", "auto"):
        Config.load().set("mode", mode)
        _audit_web(request, "mode", mode)
    return RedirectResponse("/settings", status_code=303)


@app.post("/settings/welcome")
def settings_welcome(request: Request, welcome: str = Form(...)):
    redir = _need_auth(request)
    if redir:
        return redir
    Config.load().set("welcome", welcome)
    _audit_web(request, "welcome")
    return RedirectResponse("/settings", status_code=303)


@app.get("/settings/2fa-setup", response_class=HTMLResponse)
def totp_setup_page(request: Request):
    redir = _need_auth(request)
    if redir:
        return redir
    if TOTP_FILE.exists():
        return RedirectResponse("/settings", status_code=303)
    secret = pyotp.random_base32()
    tok = request.cookies.get("session")
    PENDING_TOTP[tok] = (secret, datetime.now(timezone.utc) + timedelta(minutes=10))
    url = pyotp.TOTP(secret).provisioning_uri(name="Gold Council", issuer_name="Gold Council")
    body = f"""<div class="card">افتح تطبيق Authenticator (Google / Microsoft Authenticator)
وأضف الحساب يدويًا بهذا السر:<br><b>{secret}</b><br>
أو انسخ هذا الرابط في التطبيق:<br><code>{url}</code></div>
<form method="post" action="/settings/2fa-confirm">
<input name="code" placeholder="كود 6 أرقام للتأكيد" required inputmode="numeric">
<button>تأكيد وتفعيل</button></form>"""
    return layout("تفعيل المصادقة الثنائية", body)


@app.post("/settings/2fa-confirm")
def totp_confirm(request: Request, code: str = Form(...)):
    redir = _need_auth(request)
    if redir:
        return redir
    tok = request.cookies.get("session")
    pend = PENDING_TOTP.get(tok)
    if not pend or pend[1] <= datetime.now(timezone.utc):
        return HTMLResponse(layout("خطأ", "<p class='bad'>انتهت صلاحية الإعداد — ابدأ من جديد من الإعدادات</p>"))
    secret = pend[0]
    if not pyotp.TOTP(secret).verify(code.strip(), valid_window=1):
        _audit_web(request, "2fa-enable", ok=0)
        return HTMLResponse(layout("خطأ", "<p class='bad'>كود غير صحيح — جرّب مجددًا</p>"))
    TOTP_FILE.write_text(secret)
    TOTP_FILE.chmod(0o600)
    PENDING_TOTP.pop(tok, None)
    _audit_web(request, "2fa-enable", ok=1)
    return RedirectResponse("/settings", status_code=303)


@app.post("/settings/2fa-disable")
def totp_disable(request: Request, code: str = Form(...)):
    redir = _need_auth(request)
    if redir:
        return redir
    if not TOTP_FILE.exists():
        return RedirectResponse("/settings", status_code=303)
    secret = TOTP_FILE.read_text().strip()
    if not pyotp.TOTP(secret).verify(code.strip(), valid_window=1):
        _audit_web(request, "2fa-disable", ok=0)
        return HTMLResponse(layout("خطأ", "<p class='bad'>كود غير صحيح — لم يُلغَ التفعيل</p>"))
    TOTP_FILE.unlink()
    _audit_web(request, "2fa-disable", ok=1)
    return RedirectResponse("/settings", status_code=303)
