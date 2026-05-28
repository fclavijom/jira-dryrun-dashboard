#!/bin/bash
cd "$(dirname "$0")"

# Streamlit app
if [ -f app.pid ]; then
  PID=$(cat app.pid)
  if kill -0 "$PID" 2>/dev/null; then
    kill "$PID" && echo "Streamlit detenido (PID $PID)"
  else
    echo "Streamlit no estaba corriendo"
  fi
  rm -f app.pid
fi

# Notify proxy
if [ -f proxy.pid ]; then
  PID=$(cat proxy.pid)
  if kill -0 "$PID" 2>/dev/null; then
    kill "$PID" && echo "Proxy detenido (PID $PID)"
  else
    echo "Proxy no estaba corriendo"
  fi
  rm -f proxy.pid
fi
