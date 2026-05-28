#!/bin/bash
cd "$(dirname "$0")"

if [ -f app.pid ] && kill -0 "$(cat app.pid)" 2>/dev/null; then
  echo "La app ya está corriendo (PID $(cat app.pid))"
  exit 0
fi

nohup venv/bin/streamlit run app.py > streamlit.log 2>&1 &
echo $! > app.pid
echo "App iniciada (PID $!) — http://localhost:8501"
