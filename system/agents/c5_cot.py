"""C5 — تمركز المؤسسات (COT): صافي تمركز المضاربين في عقود الذهب.

المصدر: ملف CFTC النصي المجاني (Traders in Financial Futures).
القاعدة الصارمة: أي فشل في الجلب أو التحليل → degraded بـ signal=0.
لا تُخترع أرقام أبدًا.
"""
import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

COT_URL = "https://www.cftc.gov/dea/newcot/financials.txt"
CACHE = Path(__file__).parent.parent / "data" / "cot_cache.json"

# COT أسبوعي — الجلب مرة واحدة لكل عملية (إلا كانت حلقة E2 ستعلّق)
_MEM = {"at": 0.0, "text": None}
_TTL = 24 * 3600


def _fetch_cot_text() -> str | None:
    import time
    if time.time() - _MEM["at"] < _TTL:
        return _MEM["text"]  # يشمل التخزين السلبي (None بعد فشل)
    try:
        req = urllib.request.Request(COT_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=25) as r:
            _MEM.update(at=time.time(), text=r.read().decode("utf-8", errors="ignore"))
            return _MEM["text"]
    except Exception:
        _MEM["at"] = time.time()  # تخزين سلبي: لا تعيد المحاولة قبل TTL
        return _MEM["text"]  # قد يكون None → degraded بشرف


def _parse_gold_net(text: str) -> dict | None:
    """يستخرج: إجمالي العقود، صافي المضاربين كنسبة مئوية."""
    for line in text.splitlines():
        if "GOLD - COMMODITY EXCHANGE" not in line:
            continue
        nums = [int(x.replace(",", "")) for x in re.findall(r"[\d,]+", line)]
        # التخطيط: [OI, NC long, NC short, NC spreads, Comm long, Comm short, ...]
        if len(nums) < 6 or nums[0] <= 0:
            return None
        oi, nc_long, nc_short = nums[0], nums[1], nums[2]
        if nc_long > oi or nc_short > oi:
            return None
        net_pct = (nc_long - nc_short) / oi
        return {"oi": oi, "nc_long": nc_long, "nc_short": nc_short,
                "net_pct": round(net_pct, 4)}
    return None


def analyze() -> dict:
    degraded = {"agent": "C5", "signal": 0, "confidence": 0,
                "detail": "تعذر تحليل COT — degraded"}
    text = _fetch_cot_text()
    if not text:
        return degraded
    parsed = _parse_gold_net(text)
    if not parsed:
        return degraded

    net = parsed["net_pct"]
    prev = None
    try:
        if CACHE.exists():
            prev = json.loads(CACHE.read_text(encoding="utf-8")).get("net_pct")
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps({**parsed,
                                     "at": datetime.now(timezone.utc).isoformat()}),
                         encoding="utf-8")
    except Exception:
        pass

    detail = f"صافي المضاربين في الذهب: {net:+.1%} من العقود المفتوحة"
    signal, conf = 0, 0
    if prev is not None:
        delta = net - prev
        detail += f" (التغير الأسبوعي {delta:+.1%})"
        if delta > 0.02:
            signal, conf = 1, 65
            detail += " — المضاربون يضيفون مراكز شرائية"
        elif delta < -0.02:
            signal, conf = -1, 65
            detail += " — المضاربون يخفضون مراكزهم"
    elif abs(net) > 0.35:
        # تمركز متطرف = إشارة انعكاسية (contrarian) بحذر
        signal, conf = (-1 if net > 0 else 1), 55
        detail += " — تمركز متطرف (قراءة انعكاسية حذرة)"
    return {"agent": "C5", "signal": signal, "confidence": conf,
            "detail": detail, "net_pct": net}
