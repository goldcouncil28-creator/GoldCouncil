"""M2 — مدير المخاطر: الأرقام فقط. كود خالص، فيتو مطلق.

- حجم الصفقة: مخاطرة ثابتة RISK_PCT من رأس المال.
- الوقف: 1.5 × ATR. الأهداف: TP1 = 2R، TP2 = 3R (أو أهداف فيبوناتشي إن وُجدت).
- يبني بطاقة التوصية النهائية بالعربية.
"""
from dataclasses import dataclass, asdict

RISK_PCT = 0.01          # 1% مخاطرة للصفقة
ACCOUNT_USD = 10_000     # رأس المال الورقي الافتراضي
SL_ATR_MULT = 1.5
MAX_SIGNALS_PER_DAY = 3


@dataclass
class SignalCard:
    symbol: str
    direction: str        # "شراء" / "بيع"
    entry: float
    stop: float
    tp1: float
    tp2: float
    confidence: int
    risk_reward: float
    risk_usd: float
    size_oz: float        # حجم الصفقة (أونصة للدهب)
    analysis: str
    validity_hours: int = 8

    def text(self) -> str:
        emoji = "🟢" if self.direction == "شراء" else "🔴"
        return (
            f"{emoji} {self.direction} {self.symbol}\n"
            f"الدخول: {self.entry:,.2f}\n"
            f"وقف الخسارة: {self.stop:,.2f} ({abs(self.entry - self.stop):.2f}$)\n"
            f"الهدف 1: {self.tp1:,.2f} | الهدف 2: {self.tp2:,.2f}\n"
            f"الثقة: {self.confidence}% | المخاطرة/العائد: 1:{self.risk_reward:.1f}\n"
            f"📊 التحليل: {self.analysis}\n"
            f"⏱️ الصلاحية: {self.validity_hours} ساعات | M2: مخاطرة {RISK_PCT:.0%} "
            f"(${self.risk_usd:,.0f}) | الحجم: {self.size_oz:.2f} أونصة"
        )


def build_signal(symbol: str, direction: int, entry: float, atr_value: float,
                 confidence: float, reasons: list,
                 fib_targets: list | None = None) -> SignalCard | None:
    """يبني البطاقة أو يرجع None لو الأرقام غير صالحة (فيتو)."""
    if direction == 0 or atr_value <= 0 or entry <= 0:
        return None  # فيتو M2
    sl_dist = SL_ATR_MULT * atr_value
    stop = entry - sl_dist * direction
    # TP1 ثابت = 1.5R (معدل إصابة قابل للنشر) — TP2 امتداد فيبوناتشي أو 3R
    tp1 = entry + 1.5 * sl_dist * direction
    fib_tp = None
    if fib_targets:
        for t in fib_targets:
            if (direction == 1 and t > tp1) or (direction == -1 and t < tp1):
                fib_tp = t
                break
    tp2 = fib_tp if fib_tp else entry + 3 * sl_dist * direction

    risk_usd = ACCOUNT_USD * RISK_PCT
    size_oz = risk_usd / sl_dist if sl_dist > 0 else 0
    rr = abs(tp1 - entry) / sl_dist if sl_dist else 0
    analysis = " + ".join(reasons[:3]) if reasons else "إجماع الوكلاء"

    return SignalCard(
        symbol=symbol,
        direction="شراء" if direction == 1 else "بيع",
        entry=round(entry, 2), stop=round(stop, 2),
        tp1=round(tp1, 2), tp2=round(tp2, 2),
        confidence=int(confidence), risk_reward=round(rr, 1),
        risk_usd=risk_usd, size_oz=round(size_oz, 2),
        analysis=analysis,
    )
