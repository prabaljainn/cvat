#!/bin/bash

# CVAT Frontend Development Server Startup Script

set -e

echo "🎨 Starting CVAT Frontend Development Server..."

# Start the UI development server
echo "Starting React development server..."
echo "Frontend will be available at: http://localhost:3000"
echo "Backend API should be running at: http://localhost:8000"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

echo "🔄 Stopping any existing frontend processes..."
pkill -f webpack 2>/dev/null || true
sleep 2

echo "🎨 Starting CVAT Frontend with correct proxy configuration..."
cd cvat-ui && ../node_modules/.bin/webpack serve --env API_URL=http://localhost:8000 --config ./webpack.config.js --mode=development
