#!/bin/bash
cd "$(dirname "$0")"

# Streamlit app
if [ -f app.pid ] && kill -0 "$(cat app.pid)" 2>/dev/null; then
  echo "Streamlit ya está corriendo (PID $(cat app.pid))"
else
  nohup venv/bin/streamlit run app.py > streamlit.log 2>&1 &
  echo $! > app.pid
  echo "Streamlit iniciado (PID $!) — http://localhost:8501"
fi

# Notify proxy (port 7432)
if [ -f proxy.pid ] && kill -0 "$(cat proxy.pid)" 2>/dev/null; then
  echo "Proxy ya está corriendo (PID $(cat proxy.pid))"
else
  nohup /usr/bin/python3 ~/.local/bin/dryrun-proxy.py > proxy.log 2>&1 &
  echo $! > proxy.pid
  echo "Proxy iniciado (PID $!) — localhost:7432"
fi
