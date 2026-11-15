"""اختبار تأمين الداشبورد — TestClient، بلا شبكة خارجية.

يغطي: دخول صحيح/خاطئ + هاش Argon2id + توافق SHA256 قديم +
قفل بعد 5 محاولات فاشلة + جلسة 12 ساعة + خروج +
TOTP (إعداد + دخول بخطوتين + إلغاء) + سجل التدقيق +
set_password.py (هاش + حذف ملف النص).
"""
import hashlib
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pyotp
from argon2 import PasswordHasher
from fastapi.testclient import TestClient

import dashboard.app as app_mod
from dashboard.app import app
from telegram_bot import store
import telegram_bot.config as config_mod

PW = "correct-horse-battery"


def setup(tmp: Path):
    store.DB = tmp / "subs.db"
    config_mod.CONFIG_FILE = tmp / "bot_config.json"
    app_mod.PASS_FILE = tmp / ".admin-password"
    app_mod.TOTP_FILE = tmp / ".totp-secret"
    app_mod.JOURNAL_DB = tmp / "journal.db"
    app_mod.PASS_FILE.write_text(PasswordHasher().hash(PW))
    app_mod.PASS_FILE.chmod(0o600)


def clear_attempts():
    with store.conn() as c:
        c.execute("DELETE FROM login_attempts")


def audit_actions():
    with store.conn() as c:
        return [r[0] for r in c.execute("SELECT action FROM admin_audit ORDER BY id")]


def login_ok(client):
    r = client.post("/login", data={"password": PW}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/", f"login failed: {r.status_code}"
    return r


def main():
    tmp = Path(tempfile.mkdtemp())
    setup(tmp)

    # A. دخول صحيح + جلسة + صفحات + عمليات تُسجَّل
    c = TestClient(app)
    r = c.get("/", follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"] == "/login", "unauthenticated / not redirected"
    login_ok(c)
    r = c.get("/")
    assert r.status_code == 200 and "داشبورد بوت التوصيات" in r.text, "overview missing"
    r = c.get("/audit")
    assert r.status_code == 200 and "web:login" in r.text, "audit page missing login row"
    tok = c.cookies.get("session")
    assert tok, "no session cookie"
    app_mod.SESSIONS[tok] = datetime.now(timezone.utc) - timedelta(hours=1)
    r = c.get("/", follow_redirects=False)
    assert r.status_code == 307, "expired session still authed"
    login_ok(c)
    r = c.post("/subscribers/activate",
               data={"chat_id": 777, "name": "Test", "days": 30}, follow_redirects=False)
    assert r.status_code == 303, f"activate failed: {r.status_code}"
    with store.conn() as cc:
        assert cc.execute("SELECT status FROM subscribers WHERE chat_id=777").fetchone()[0] == "active"
    assert "web:activate" in audit_actions(), "activate not audited"
    r = c.post("/payments", data={"subscriber_chat_id": 777, "amount": 50, "currency": "USD",
                                  "method": "تحويل", "period_days": 30, "note": ""},
               follow_redirects=False)
    assert r.status_code == 303
    assert "web:payment" in audit_actions(), "payment not audited"
    r = c.post("/settings/mode", data={"mode": "auto"}, follow_redirects=False)
    assert r.status_code == 303
    assert "web:mode" in audit_actions(), "mode change not audited"
    c.post("/settings/mode", data={"mode": "review"}, follow_redirects=False)
    r = c.get("/logout", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login", "logout failed"
    r = c.get("/", follow_redirects=False)
    assert r.status_code == 307, "still authed after logout"

    # B. توافق SHA256 قديم
    app_mod.PASS_FILE.write_text(hashlib.sha256("legacy-pw".encode()).hexdigest())
    c2 = TestClient(app)
    r = c2.post("/login", data={"password": "legacy-pw"}, follow_redirects=False)
    assert r.status_code == 303, "legacy sha256 login failed"
    app_mod.PASS_FILE.write_text(PasswordHasher().hash(PW))

    # C. TOTP: إعداد + دخول بخطوتين + إلغاء
    c3 = TestClient(app)
    login_ok(c3)
    r = c3.get("/settings/2fa-setup")
    assert r.status_code == 200 and "Authenticator" in r.text, "2fa setup page missing"
    m = re.search(r"<b>([A-Z2-7]{16,})</b>", r.text)
    assert m, "totp secret not shown"
    secret = m.group(1)
    r = c3.post("/settings/2fa-confirm", data={"code": "000000"}, follow_redirects=False)
    assert r.status_code == 200 and "غير صحيح" in r.text, "wrong totp code accepted"
    r = c3.post("/settings/2fa-confirm",
                data={"code": pyotp.TOTP(secret).now()}, follow_redirects=False)
    assert r.status_code == 303, f"totp confirm failed: {r.status_code}"
    assert app_mod.TOTP_FILE.exists(), "totp secret not saved"
    c4 = TestClient(app)
    r = c4.post("/login", data={"password": PW}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login-2fa", "no 2fa step after login"
    r = c4.get("/login-2fa")
    assert r.status_code == 200 and "6 أرقام" in r.text, "2fa page missing"
    r = c4.post("/login-2fa", data={"code": "000000"})
    assert "غير صحيح" in r.text, "wrong 2fa code accepted"
    r = c4.post("/login-2fa", data={"code": pyotp.TOTP(secret).now()}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/", "2fa login failed"
    r = c4.get("/")
    assert r.status_code == 200, "not authed after 2fa"
    r = c4.post("/settings/2fa-disable", data={"code": pyotp.TOTP(secret).now()},
                follow_redirects=False)
    assert r.status_code == 303 and not app_mod.TOTP_FILE.exists(), "2fa disable failed"

    # D. قفل بعد 5 محاولات فاشلة
    clear_attempts()
    c5 = TestClient(app)
    for _ in range(5):
        r = c5.post("/login", data={"password": "wrong-pw"})
        assert r.status_code == 200 and "كلمة مرور خاطئة" in r.text, "wrong pw not rejected"
    r = c5.post("/login", data={"password": "wrong-pw"})
    assert r.status_code == 429 and "محاولات كثيرة" in r.text, f"no lockout: {r.status_code}"
    r = c5.post("/login", data={"password": PW})
    assert r.status_code == 429, "correct pw bypassed lockout"
    assert "web:login" in audit_actions(), "failed logins not audited"

    # E. set_password.py: هاش Argon2id + حذف ملف النص
    helper_src = Path(__file__).parent / "set_password.py"
    helper = tmp / "set_password.py"
    helper.write_text(helper_src.read_text(encoding="utf-8"))
    pw_file = tmp / "pw.txt"
    pw_file.write_text("my-secret-pw-123\n")
    out = subprocess.run([sys.executable, str(helper), str(pw_file)],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, f"set_password failed: {out.stdout} {out.stderr}"
    assert not pw_file.exists(), "plaintext password file not deleted"
    h = (tmp / ".admin-password").read_text()
    assert h.startswith("$argon2id$"), "hash is not Argon2id"
    assert PasswordHasher().verify(h, "my-secret-pw-123"), "hash does not verify"
    short_file = tmp / "short.txt"
    short_file.write_text("short")
    out = subprocess.run([sys.executable, str(helper), str(short_file)],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode != 0 and short_file.exists(), "short password accepted"

    print("ALL DASHBOARD AUTH TESTS PASSED")


if __name__ == "__main__":
    main()
