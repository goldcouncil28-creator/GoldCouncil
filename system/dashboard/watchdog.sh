#!/bin/bash
# حارس الداشبورد: يعيد التشغيل لو توقف (يُستدعى كل 15 دقيقة عبر cron)
if curl -s -m 5 -o /dev/null http://127.0.0.1:8100/; then
  exit 0
fi
DIR="$HOME/workspace/goals/goal/system/dashboard"
nohup "$DIR/run.sh" >> "$DIR/server.log" 2>&1 &
echo "dashboard restarted"
