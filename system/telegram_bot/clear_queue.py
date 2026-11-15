"""تنظيف طابور تحديثات تيليجرام العالق — يُشغَّل مرة واحدة يدويًا.

يستدعي deleteWebhook مع drop_pending_updates=true فيمسح أي تحديثات
معلّقة في خوادم تيليجرام، ثم يتحقق أن getUpdates أصبح فارغًا.
آمن فقط بعد التأكد أن لا تحديثات شرعية بانتظار المعالجة
(تحقّقنا 2026-11-07 21:48: الطابور كان فارغًا، offset 284405746).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from telegram_bot.api import BotApi
from telegram_bot.config import Config, DIR

OFFSET_FILE = DIR / ".offset"


def main() -> int:
    cfg = Config.load()
    if not cfg.configured:
        print("clear_queue: not configured, skipping")
        return 0
    api = BotApi(cfg.token)
    offset = int(OFFSET_FILE.read_text()) if OFFSET_FILE.exists() else 0
    before = api.get_updates(offset, timeout=5)
    print(f"clear_queue: pending before clear: {len(before)}")
    result = api.delete_webhook(drop_pending_updates=True)
    print(f"clear_queue: deleteWebhook -> {result}")
    after = api.get_updates(offset, timeout=5)
    print(f"clear_queue: pending after clear: {len(after)}")
    return 0 if not after else 1


if __name__ == "__main__":
    raise SystemExit(main())
