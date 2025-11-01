#!/bin/bash

echo "Git pull main repository..."
git pull

# Get the parent directory and project name
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_NAME="$(basename "$PROJECT_DIR")"
ANALYSIS_DIR="$(dirname "$PROJECT_DIR")/analysis"

# If analysis directory exists, pull there too
if [ -d "$ANALYSIS_DIR" ]; then
    echo "Git pull analysis repository..."
    cd "$ANALYSIS_DIR"
    git pull
    cd "$PROJECT_DIR"
else
    echo "Analysis directory not found at $ANALYSIS_DIR, skipping..."
fi

echo "Stop tasks..."
pkill -f process_tasks

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"$DIR/entrypoint.sh"

echo "Graceful restart..."

# Path to the Gunicorn PID file
PIDFILE="gunicorn.pid"

# Check if the PID file exists
if [ ! -f "$PIDFILE" ]; then
    echo "PID file not found: $PIDFILE"
    exit 1
fi

# Get the master process PID
MASTER_PID=$(cat "$PIDFILE")

# Get the PIDs of the child worker processes
WORKER_PIDS=$(pgrep -P "$MASTER_PID")

# Check if any workers were found
if [ -z "$WORKER_PIDS" ]; then
    echo "No workers found for master PID $MASTER_PID"
    exit 1
fi

# Iterate over each worker PID and send the TERM signal with a delay
for PID in $WORKER_PIDS; do
    echo "Terminating worker PID: $PID"
    kill -TERM "$PID"

    # Wait 20 seconds before proceeding to the next worker
    sleep 20
done
