"""إعدادات بوت التوصيات — ملف JSON + التوكن في ملف منفصل (600).

كل السكربتات config-gated: لو التوكن أو القناة غير موجودين،
تخرج بهدوء (exit 0) بلا إرسال — الكرونات آمنة قبل التفعيل.
"""
import json
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
        return cls(merged)

    def save(self):
        CONFIG_FILE.write_text(json.dumps(self._data, ensure_ascii=False, indent=1),
                               encoding="utf-8")

    def __getattr__(self, name):
        return self._data.get(name)

    def set(self, name, value):
        self._data[name] = value
        self.save()

    @property
    def token(self) -> str | None:
        p = Path(self._data["token_file"])
        if p.exists():
            t = p.read_text(encoding="utf-8").strip()
            return t or None
        return None

    @property
    def configured(self) -> bool:
        return bool(self.token and self._data.get("channel_id")
                    and self._data.get("admin_ids"))
