#!/bin/bash
# تشغيل داشبورد بوت التوصيات على 127.0.0.1:8100
cd "$(dirname "$0")/.."
exec venv/bin/python -m uvicorn dashboard.app:app --host 127.0.0.1 --port 8100
