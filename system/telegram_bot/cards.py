"""نصوص البطاقات ولوحات الأزرار.

البطاقة = card.text() من M2 + وسم الورقي + زر الدخول الذاتي.
"""
PAPER_TAG = "\n🧪 ورقي — للاختبار والتوثيق، ليست نصيحة مالية"


def channel_card(card_text: str, mode: str = "paper") -> str:
    text = card_text
    if mode == "paper":
        text += PAPER_TAG
    return text


def entered_keyboard(signal_id: int) -> dict:
    return {"inline_keyboard": [[
        {"text": "دخلت الصفقة ✅", "callback_data": f"entered:{signal_id}"}]]}


def review_keyboard(signal_id: int) -> dict:
    return {"inline_keyboard": [[
        {"text": "✅ اعتماد ونشر", "callback_data": f"approve:{signal_id}"},
        {"text": "❌ رفض", "callback_data": f"reject:{signal_id}"}]]}


def panel_main_keyboard() -> dict:
    return {"inline_keyboard": [
        [{"text": "👥 المشتركون", "callback_data": "panel:subs"},
         {"text": "📥 بانتظار المراجعة", "callback_data": "panel:pending"}],
        [{"text": "📊 الإحصائيات", "callback_data": "panel:stats"},
         {"text": "⚙️ الوضع", "callback_data": "panel:mode"}],
        [{"text": "🧾 سجل العمليات", "callback_data": "panel:audit"}],
    ]}


def panel_back_keyboard(back_to: str = "panel:main") -> dict:
    return {"inline_keyboard": [[
        {"text": "⬅️ رجوع", "callback_data": back_to}]]}


def result_line(status: str, pnl_r: float | None) -> str:
    if status == "tp1":
        return f"\n\n✅ تحقق الهدف 1 (+1.5R)"
    if status == "tp2":
        return f"\n\n✅ تحقق الهدف 2 (+{pnl_r:.1f}R)" if pnl_r else "\n\n✅ تحقق الهدف 2"
    if status == "sl":
        return "\n\n❌ ضرب وقف الخسارة (-1R)"
    if status == "expired":
        return f"\n\n⏱️ انتهت الصلاحية ({pnl_r:+.2f}R)" if pnl_r is not None else "\n\n⏱️ انتهت الصلاحية — سعر الإغلاق غير متاح"
    return ""
