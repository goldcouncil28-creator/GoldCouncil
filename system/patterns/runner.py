"""Pattern 03 — Parallelization + Pattern 01 — Prompt Chaining.

القاعدة (من ARCHITECTURE.md): كل ما هو مستقل يعمل بالتوازي؛
التسلسل فقط لما له اعتماد بيانات حقيقي.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed

# executor مشترك لكل العملية — إنشاؤه مع كل شمعة كان أغلب التكلفة
_EXECUTOR = None


def _executor(max_workers: int = 10) -> ThreadPoolExecutor:
    global _EXECUTOR
    if _EXECUTOR is None:
        _EXECUTOR = ThreadPoolExecutor(max_workers=max_workers,
                                       thread_name_prefix="agent")
    return _EXECUTOR


def run_parallel(tasks: list, max_workers: int = 10) -> dict:
    """tasks: [(name, fn, args_tuple, kwargs_dict)] → {name: result|{"error":...}}"""
    out = {}
    ex = _executor(max_workers)
    futs = {ex.submit(fn, *(a or ()), **(k or {})): name
            for name, fn, a, k in tasks}
    for f in as_completed(futs):
        name = futs[f]
        try:
            out[name] = f.result()
        except Exception as e:
            out[name] = {"agent": name, "signal": 0, "confidence": 0,
                         "detail": f"خطأ: {type(e).__name__} — مُستبعد"}
    return out


def chain(steps: list, initial):
    """Prompt Chaining: مخرج كل خطوة = مدخل التالية. أي خطوة ترجع None توقف السلسلة."""
    data = initial
    for step in steps:
        if data is None:
            return None
        data = step(data)
    return data
