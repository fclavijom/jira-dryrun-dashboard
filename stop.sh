#!/bin/bash
cd "$(dirname "$0")"

if [ ! -f app.pid ]; then
  echo "No se encontró app.pid — la app no está corriendo"
  exit 0
fi

PID=$(cat app.pid)
if kill -0 "$PID" 2>/dev/null; then
  kill "$PID"
  rm app.pid
  echo "App detenida (PID $PID)"
else
  rm app.pid
  echo "La app no estaba corriendo (PID $PID ya no existe)"
fi
