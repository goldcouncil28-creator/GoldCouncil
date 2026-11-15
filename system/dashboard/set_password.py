"""تعيين كلمة مرور الداشبورد: يقرأ كلمة المرور من ملف نصي، يخزن هاش
Argon2id في dashboard/.admin-password (600)، ثم يحذف ملف النص الأصلي.

الاستخدام:
  venv/bin/python dashboard/set_password.py /path/to/password.txt
"""
import sys
from pathlib import Path

from argon2 import PasswordHasher


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: set_password.py <password-file>")
        return 2
    src = Path(sys.argv[1])
    pw = src.read_text(encoding="utf-8").strip()
    if len(pw) < 8:
        print("password too short (min 8 chars)")
        return 2
    dst = Path(__file__).parent / ".admin-password"
    dst.write_text(PasswordHasher().hash(pw))
    dst.chmod(0o600)
    src.unlink()
    print("password set (Argon2id hash stored, plaintext file deleted)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
