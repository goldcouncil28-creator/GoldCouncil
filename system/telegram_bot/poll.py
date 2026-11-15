"""استطلاع أوامر البوت لمرة واحدة (يُشغَّل كل دقيقتين عبر cron).

يعالج الرسائل والأزرار ثم يحفظ الـ offset — آمن للتكرار.

حماية منع التكرار (2026-11-07، بعد فيضان 2026-11-06):
تيليجرام أعاد تسليم نفس الـ updates (284404602–284404610) كل دورة
~3 ساعات رغم تقدّم الـ offset، فأعاد البوت إرسال لوحة الأدمن ~190 مرة.
الآن طبقتان:
  1) أي update_id أصغر من الـ offset عند بداية الدورة سبق تمريره
     في دورة سابقة → يُتخطَّى دون معالجة.
  2) جدول processed_updates في subs.db يتذكّر آخر 2000 update_id
     معالَج عبر الدورات (كل دورة عملية جديدة) → المعاد يُتخطَّى.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from telegram_bot.api import BotApi
from telegram_bot.config import Config, DIR
from telegram_bot import commands, store

OFFSET_FILE = DIR / ".offset"


def main() -> int:
    cfg = Config.load()
    if not cfg.configured:
        print("poll: not configured, skipping")
        return 0
    api = BotApi(cfg.token)
    offset = int(OFFSET_FILE.read_text()) if OFFSET_FILE.exists() else 0
    try:
        updates = api.get_updates(offset, timeout=10)
    except Exception as e:
        print(f"poll: getUpdates failed: {type(e).__name__}")
        return 1
    new_max = offset
    processed = skipped = 0
    with store.conn() as c:
        for u in updates:
            uid = u.get("update_id")
            if uid is None:
                continue
            new_max = max(new_max, uid)
            # طبقة 1: أقدم من الـ offset الابتدائي = سبق تمريره في دورة سابقة.
            # طبقة 2: مسجَّل في processed_updates = سبق معالجته.
            if uid < offset or store.is_processed(c, uid):
                skipped += 1
                continue
            try:
                commands.handle_update(api, cfg, u)
            except Exception as e:
                print(f"poll: update {uid} error: {type(e).__name__}")
                continue
            store.mark_processed(c, uid, datetime.now(timezone.utc).isoformat())
            processed += 1
    OFFSET_FILE.write_text(str(new_max + 1))
    print(f"poll: {processed} updates processed, {skipped} duplicates skipped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
