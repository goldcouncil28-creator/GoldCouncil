"""استطلاع أوامر البوت لمرة واحدة (يُشغَّل كل 5 دقائق عبر GitHub Actions).

يعالج الرسائل والأزرار ثم يحفظ الـ offset — آمن للتكرار.
التخزين عبر `backend` (SQLite محليًا، Supabase على Actions).

حماية منع التكرار (2026-11-07، بعد فيضان 2026-11-06):
تيليجرام أعاد تسليم نفس الـ updates (284404602–284404610) كل دورة
~3 ساعات رغم تقدّم الـ offset، فأعاد البوت إرسال لوحة الأدمن ~190 مرة.
الآن طبقتان:
  1) أي update_id أصغر من الـ offset عند بداية الدورة سبق تمريره
     في دورة سابقة → يُتخطَّى دون معالجة.
  2) جدول processed_updates يتذكّر آخر 2000 update_id
     معالَج عبر الدورات (كل دورة عملية جديدة) → المعاد يُتخطَّى.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from telegram_bot.api import BotApi
from telegram_bot.config import Config
from telegram_bot import backend, commands


def main() -> int:
    cfg = Config.load()
    if not cfg.configured:
        print("poll: not configured, skipping")
        return 0
    api = BotApi(cfg.token)
    store = backend.get_backend()
    offset = store.get_offset()
    try:
        updates = api.get_updates(offset, timeout=10)
    except Exception:
        print("poll: getUpdates failed")
        return 1
    new_max = offset
    processed = skipped = 0
    for u in updates:
        uid = u.get("update_id")
        if uid is None:
            continue
        new_max = max(new_max, uid)
        # طبقة 1: أقدم من الـ offset الابتدائي = سبق تمريره في دورة سابقة.
        # طبقة 2: مسجَّل في processed_updates = سبق معالجته.
        if uid < offset or store.is_processed(uid):
            skipped += 1
            continue
        try:
            commands.handle_update(api, cfg, u)
        except Exception as e:
            print(f"poll: update {uid} error: {type(e).__name__}")
            continue
        store.mark_processed(uid)
        processed += 1
    store.set_offset(new_max + 1)
    print(f"poll: {processed} updates processed, {skipped} duplicates skipped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
