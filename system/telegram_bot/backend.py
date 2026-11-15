"""Backend switch for the bot runtime.

`GC_STORE=supabase` → `sb_store` (Supabase, GitHub Actions hosting).
Anything else (default) → `sqlite_backend` (the original on-disk SQLite
behaviour, unchanged).

Resolved once per process — the store is process-level configuration.
"""
import os

_BACKEND = None


def use_supabase() -> bool:
    return os.environ.get("GC_STORE", "").strip().lower() == "supabase"


def get_backend():
    global _BACKEND
    if _BACKEND is None:
        if use_supabase():
            from . import sb_store as backend
        else:
            from . import sqlite_backend as backend
        _BACKEND = backend
    return _BACKEND


def reset_backend():
    """Tests only: forget the cached backend so a GC_STORE change applies."""
    global _BACKEND
    _BACKEND = None
