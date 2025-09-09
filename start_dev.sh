#!/bin/bash

# CVAT Development Environment Startup Script
# This script starts the CVAT development environment with live Python code changes

set -e

echo "🚀 Starting CVAT Development Environment..."

# Set required environment variables for macOS
export DYLD_LIBRARY_PATH="/opt/homebrew/lib:$DYLD_LIBRARY_PATH"
export PKG_CONFIG_PATH="/opt/homebrew/lib/pkgconfig:$PKG_CONFIG_PATH"

# Activate virtual environment
echo "📦 Activating Python virtual environment..."
source .env/bin/activate

# Stop any existing Django processes
echo "🔄 Stopping existing Django processes..."
pkill -f "manage.py runserver" 2>/dev/null || true
sleep 2

# Check if Docker services are running
echo "🐳 Checking Docker services..."
if ! docker compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.dev-local.yml ps | grep -q "Up"; then
    echo "Starting Docker services..."
    docker compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.dev-local.yml up -d cvat_opa cvat_db cvat_redis_inmem cvat_redis_ondisk
    echo "Waiting for services to be ready..."
    sleep 10
fi

# Start RQ workers for task processing
echo "🔧 Starting RQ workers for task processing..."
python manage.py rqworker import --verbosity=1 &
IMPORT_WORKER_PID=$!
python manage.py rqworker chunks --verbosity=1 &
CHUNKS_WORKER_PID=$!
echo "Started workers: import (PID: $IMPORT_WORKER_PID), chunks (PID: $CHUNKS_WORKER_PID)"

# Start the Django development server
echo "🌐 Starting Django development server..."
echo "Backend will be available at: http://localhost:8000"
echo "Admin interface: http://localhost:8000/admin (admin/admin123456)"
echo ""
echo "To start the frontend development server, run in another terminal:"
echo "  ./start_frontend.sh"
echo "Frontend will be available at: http://localhost:3000"
echo ""
echo "Press Ctrl+C to stop the server and workers"
echo ""

# Function to cleanup workers on exit
cleanup() {
    echo "🛑 Stopping workers..."
    kill $IMPORT_WORKER_PID $CHUNKS_WORKER_PID 2>/dev/null || true
    exit
}
trap cleanup INT TERM

# Run the Django server with the correct environment
python manage.py runserver --settings=cvat.settings.development 0.0.0.0:8000
