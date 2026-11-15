"""رسم صورة التحليل لكل توصية — زي باقي جروبات التوصيات.

شموع H1 (آخر 80 شمعة) + خطوط الدخول/الوقف/الأهداف + وسم الورقي.
إخراج PNG جاهز للإرسال كصورة مع البطاقة.
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

DIR = Path(__file__).parent / "charts"


def render_signal_chart(df, card, path: Path | None = None) -> Path:
    """df: شموع H1 حتى لحظة الإشارة. card: بطاقة M2 (entry/stop/tp1/tp2)."""
    d = df.tail(80)
    DIR.mkdir(parents=True, exist_ok=True)
    path = path or (DIR / f"signal_{card.symbol}_{len(df)}.png")

    fig, ax = plt.subplots(figsize=(12, 7), dpi=100)
    fig.patch.set_facecolor("#0e1117")
    ax.set_facecolor("#0e1117")

    x = np.arange(len(d))
    opens = d["open"].to_numpy()
    highs = d["high"].to_numpy()
    lows = d["low"].to_numpy()
    closes = d["close"].to_numpy()
    up = closes >= opens
    ax.vlines(x, lows, highs, color=np.where(up, "#26a69a", "#ef5350"),
              linewidth=1)
    ax.bar(x[up], closes[up] - opens[up], bottom=opens[up], width=0.7,
           color="#26a69a")
    ax.bar(x[~up], opens[~up] - closes[~up], bottom=closes[~up], width=0.7,
           color="#ef5350")

    def hline(price, color, label):
        ax.axhline(price, color=color, linestyle="--", linewidth=1.5)
        ax.text(len(d) - 1, price, f" {label} {price:,.2f}",
                color=color, fontsize=10, va="bottom")

    hline(card.entry, "#4caf50", "دخول")
    hline(card.stop, "#ef5350", "وقف")
    hline(card.tp1, "#42a5f5", "هدف 1")
    hline(card.tp2, "#ffb300", "هدف 2")

    direction = "شراء" if card.direction == "شراء" else "بيع"
    ax.set_title(f"{card.symbol} — {direction} | ثقة {card.confidence}% | ورقي 🧪",
                 color="white", fontsize=14, pad=12)
    ax.tick_params(colors="#888888")
    for s in ax.spines.values():
        s.set_color("#333333")
    ax.grid(color="#222222", linewidth=0.5)
    try:
        fig.tight_layout()
    except Exception:
        pass
    fig.savefig(path, facecolor=fig.get_facecolor())
    plt.close(fig)
    return path
