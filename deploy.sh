#!/bin/bash

# 🚀 CVAT Custom System - Production Deployment Script
# This script automates the complete deployment process

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

success() {
    echo -e "${GREEN}✅ $1${NC}"
}

warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

error() {
    echo -e "${RED}❌ $1${NC}"
    exit 1
}

# Check if running as root
if [[ $EUID -eq 0 ]]; then
   error "This script should not be run as root for security reasons"
fi

log "🚀 Starting CVAT Custom System Deployment..."

# Step 1: Check prerequisites
log "📋 Checking prerequisites..."

# Check Docker
if ! command -v docker &> /dev/null; then
    error "Docker is not installed. Please install Docker first."
fi

# Check Docker Compose
if ! command -v docker-compose &> /dev/null; then
    error "Docker Compose is not installed. Please install Docker Compose first."
fi

# Check if user is in docker group
if ! groups $USER | grep -q '\bdocker\b'; then
    error "User $USER is not in docker group. Run: sudo usermod -aG docker $USER && logout"
fi

success "Prerequisites check passed"

# Step 2: Environment setup
log "🔧 Setting up environment..."

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    log "Creating .env file..."
    cp .env.example .env 2>/dev/null || cat > .env << 'EOF'
# CVAT Configuration
CVAT_HOST=localhost
CVAT_POSTGRES_PASSWORD=cvat_postgresql_password
CVAT_REDIS_PASSWORD=cvat_redis_password

# Analytics Configuration
CVAT_ANALYTICS_ENABLED=true
CVAT_CUSTOM_FEATURES_ENABLED=true

# Dashboard Configuration
ANGULAR_DASHBOARD_ENABLED=true

# SSL Configuration (for production)
ACME_EMAIL=admin@localhost
TRAEFIK_CERTIFICATESRESOLVERS_LETSENCRYPT_ACME_EMAIL=admin@localhost
EOF
    warning "Please edit .env file with your actual values before proceeding"
    read -p "Press Enter after editing .env file..."
fi

success "Environment configuration ready"

# Step 3: Create necessary directories and files
log "📁 Creating deployment structure..."

# Create SQL initialization directory
mkdir -p sql
if [ ! -f sql/init-analytics.sql ]; then
    cat > sql/init-analytics.sql << 'EOF'
-- Initialize analytics extensions
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Create indexes for analytics performance
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_task_created_date ON engine_task(created_date);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_task_updated_date ON engine_task(updated_date);

-- Note: Train metadata indexes will be created by Django migrations
EOF
fi

# Create Traefik configuration
mkdir -p traefik
if [ ! -f traefik/traefik.yml ]; then
    cat > traefik/traefik.yml << 'EOF'
api:
  dashboard: true
  insecure: false

entryPoints:
  web:
    address: ":80"
    http:
      redirections:
        entrypoint:
          to: websecure
          scheme: https
  websecure:
    address: ":443"

certificatesResolvers:
  letsencrypt:
    acme:
      email: ${ACME_EMAIL}
      storage: /letsencrypt/acme.json
      httpChallenge:
        entryPoint: web

providers:
  docker:
    exposedByDefault: false
EOF
fi

# Create SSL certificate storage
mkdir -p letsencrypt
touch letsencrypt/acme.json
chmod 600 letsencrypt/acme.json

success "Deployment structure created"

# Step 4: Build custom CVAT image with your APIs
log "🏗️  Building custom CVAT image with analytics APIs..."

# Build your custom CVAT image
docker-compose -f docker-compose.yml -f docker-compose.production.yml build

# Step 5: Start services
log "🚀 Starting services with custom build..."
docker-compose -f docker-compose.yml -f docker-compose.production.yml up -d

# Wait for services to be ready
log "⏳ Waiting for services to start (this may take 2-3 minutes)..."
sleep 30

# Check if services are running
if ! docker-compose ps | grep -q "Up"; then
    error "Some services failed to start. Check logs with: docker-compose logs"
fi

success "Services started successfully"

# Step 5: Initialize database
log "🗄️  Initializing database..."

# Wait for database to be ready
log "Waiting for database to be ready..."
timeout=60
while ! docker-compose exec -T cvat_db pg_isready -U root -d cvat &>/dev/null; do
    sleep 2
    timeout=$((timeout-2))
    if [ $timeout -le 0 ]; then
        error "Database failed to start within 60 seconds"
    fi
done

# Run migrations
log "Running database migrations..."
docker-compose exec -T cvat_server python manage.py migrate

# Collect static files
log "Collecting static files..."
docker-compose exec -T cvat_server python manage.py collectstatic --noinput

# Create initial train metadata for existing tasks (if any)
log "Initializing train metadata..."
docker-compose exec -T cvat_server python manage.py shell << 'EOF'
from cvat.apps.engine.models import Task
from cvat.apps.custom.models import TaskTrainMetadata

task_count = Task.objects.count()
if task_count > 0:
    for task in Task.objects.all():
        metadata, created = TaskTrainMetadata.get_or_create_for_task(task)
        if created:
            print(f"Created metadata for task {task.id}")
    print(f"Processed {task_count} tasks")
else:
    print("No existing tasks found")
EOF

success "Database initialization complete"

# Step 6: Verify deployment
log "🔍 Verifying deployment..."

# Check service health
sleep 10  # Give services a moment to fully start

# Test CVAT API
if curl -f -s http://localhost/api/server/about > /dev/null 2>&1; then
    success "CVAT API is responding"
else
    warning "CVAT API not responding yet (may need more time)"
fi

# Test Dashboard
if curl -f -s http://localhost/dashboard > /dev/null 2>&1; then
    success "Angular Dashboard is responding"
else
    warning "Dashboard not responding yet (may need more time)"
fi

# Test Custom Analytics API (will fail without auth, but should return 401, not connection error)
if curl -s http://localhost/api/custom/train-analytics/ | grep -q "Authentication credentials"; then
    success "Custom Analytics API is responding"
else
    warning "Custom Analytics API not responding yet"
fi

# Step 7: Display deployment information
log "📊 Deployment Summary"

echo ""
echo "🎉 CVAT Custom System Deployment Complete!"
echo ""
echo "📍 Access Points:"
echo "   🌐 CVAT Main UI:      http://localhost/"
echo "   📊 Analytics Dashboard: http://localhost/dashboard"
echo "   🔧 API Endpoints:     http://localhost/api/"
echo "   📈 Custom Analytics:  http://localhost/api/custom/"
echo ""
echo "🔧 Next Steps:"
echo "   1. Create admin user: docker-compose exec cvat_server python manage.py createsuperuser"
echo "   2. Configure your domain in .env for production"
echo "   3. Set up SSL certificates for HTTPS"
echo "   4. Import your data and start using the system"
echo ""
echo "📚 Documentation:"
echo "   📖 Deployment Guide: ./DEPLOYMENT_GUIDE.md"
echo "   🎯 System Overview:  ./CVAT_CUSTOM_SYSTEM_COMPLETE.md"
echo ""
echo "🔍 Monitoring:"
echo "   📊 Service Status:    docker-compose ps"
echo "   📝 Service Logs:      docker-compose logs -f [service_name]"
echo "   🏥 Health Check:      curl http://localhost/api/server/about"
echo ""

# Step 8: Optional - Create admin user
read -p "Would you like to create an admin user now? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    log "Creating admin user..."
    docker-compose exec cvat_server python manage.py createsuperuser
    success "Admin user created"
fi

# Step 9: Final health check
log "🏥 Final health check..."
sleep 5

echo ""
echo "Service Status:"
docker-compose ps

echo ""
echo "🎊 Deployment completed successfully!"
echo "Your CVAT system with custom analytics and dashboard is now running."
echo ""
echo "🚀 Happy annotating!"
