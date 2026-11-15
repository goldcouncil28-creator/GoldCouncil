"""إعدادات بوت التوصيات — ملف JSON + التوكن في ملف منفصل (600).

كل السكربتات config-gated: لو التوكن أو القناة غير موجودين،
تخرج بهدوء (exit 0) بلا إرسال — الكرونات آمنة قبل التفعيل.

على GitHub Actions (GC_STORE=supabase): التوكن من env TELEGRAM_BOT_TOKEN،
والوضع + عدد التوصيات المراجَعة من جدول bot_state في Supabase
(الملف المحلي لا يعيش عبر دورات Actions).
"""
import json
import os
from pathlib import Path

DIR = Path(__file__).parent
CONFIG_FILE = DIR / "bot_config.json"

DEFAULTS = {
    "token_file": str(DIR / ".bot-token"),
    "channel_id": None,          # يملؤها محمد: معرف القناة الخاصة (سالب)
    "admin_ids": [],             # يملؤها محمد: معرفات تيليجرام للأدمن
    "mode": "review",            # review → auto بعد 30 توصية مراجَعة
    "reviewed_count": 0,
    "auto_after_reviewed": 30,
    "expiry_warn_days": 3,
    "welcome": ("أهلًا بيك في قناة توصيات الدهب والفوركس 🥇\n"
                "التوصيات هنا للمتابعة التعليمية، والاشتراك يدوي عبر محمد.\n"
                "اكتب /stats لسجلك الشخصي و /history لآخر التوصيات."),
}


class Config:
    def __init__(self, data: dict):
        self._data = data

    @classmethod
    def load(cls) -> "Config":
        if CONFIG_FILE.exists():
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        else:
            data = {}
        merged = {**DEFAULTS, **data}
        cfg = cls(merged)
        # Supabase backend: mode + reviewed_count live in bot_state, not in
        # the ephemeral checkout. Best-effort: on any failure keep file values.
        try:
            from . import backend as _backend
            if _backend.use_supabase():
                store = _backend.get_backend()
                mode = store.get_bot_state("mode", None)
                if mode in ("review", "auto"):
                    cfg._data["mode"] = mode
                rc = store.get_bot_state("reviewed_count", None)
                if rc is not None:
                    cfg._data["reviewed_count"] = int(rc)
        except Exception:
            pass
        return cfg

    def save(self):
        CONFIG_FILE.write_text(json.dumps(self._data, ensure_ascii=False, indent=1),
                               encoding="utf-8")

    def __getattr__(self, name):
        return self._data.get(name)

    def set(self, name, value):
        self._data[name] = value
        try:
            from . import backend as _backend
            supa = _backend.use_supabase()
        except Exception:
            supa = False
        if supa and name in ("mode", "reviewed_count"):
            # Supabase backend: persist in bot_state, never in the ephemeral checkout.
            try:
                _backend.get_backend().set_bot_state(name, str(value))
            except Exception as e:
                print(f"config: bot_state write failed for {name}: {type(e).__name__}")
            return
        self.save()

    @property
    def token(self) -> str | None:
        env_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        if env_token:
            return env_token
        p = Path(self._data["token_file"])
        if p.exists():
            t = p.read_text(encoding="utf-8").strip()
            return t or None
        return None

    @property
    def configured(self) -> bool:
        return bool(self.token and self._data.get("channel_id")
                    and self._data.get("admin_ids"))
