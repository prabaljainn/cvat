# 🚀 CVAT Production Deployment Commands

Based on the [official CVAT documentation](https://docs.cvat.ai/docs/administration/basics/installation/), here are the correct deployment commands for your production setup.

---

## 📋 **Prerequisites Setup**

### **1. Environment Variables**
```bash
# Required environment variables
export CVAT_HOST=your-domain.com
export CVAT_POSTGRES_PASSWORD=your-secure-password
export ACME_EMAIL=your-email@domain.com

# Optional: Traefik dashboard authentication
export TRAEFIK_DASHBOARD_AUTH=$(htpasswd -nb admin your-dashboard-password)

# Optional: CVAT version (defaults to latest)
export CVAT_VERSION=v2.44.3
```

### **2. Create Required Directories**
```bash
# Create SSL certificate storage
mkdir -p letsencrypt
touch letsencrypt/acme.json
chmod 600 letsencrypt/acme.json

# Create analytics SQL initialization
mkdir -p sql
```

---

## 🏗️ **Deployment Commands**

### **Step 1: Build Your Custom CVAT Image**
```bash
# Build your custom CVAT image with all custom APIs
docker compose -f docker-compose.yml -f docker-compose.production.yml build

# Or build specific services
docker compose -f docker-compose.yml -f docker-compose.production.yml build cvat_server
```

### **Option 1: HTTP Only (Development/Testing)**
```bash
# Build and deploy without HTTPS
docker compose -f docker-compose.yml -f docker-compose.production.yml up -d --build
```

### **Option 2: HTTPS with Let's Encrypt (Production) - RECOMMENDED**
```bash
# Build and deploy with automatic SSL certificates
docker compose \
  -f docker-compose.yml \
  -f docker-compose.production.yml \
  -f docker-compose.https.yml \
  up -d --build
```

### **Option 3: External Database (Enterprise)**
```bash
# If using external PostgreSQL database
export CVAT_POSTGRES_HOST=your-db-host
export CVAT_POSTGRES_PORT=5432
export CVAT_POSTGRES_DBNAME=cvat
export CVAT_POSTGRES_USER=cvat_user

docker compose \
  -f docker-compose.yml \
  -f docker-compose.external_db.yml \
  -f docker-compose.production.yml \
  -f docker-compose.https.yml \
  up -d --build
```

### **Option 4: Pre-built Image (CI/CD Pipeline)**
```bash
# If you have a CI/CD pipeline that builds and pushes your image
export CVAT_CUSTOM_IMAGE=your-registry.com/cvat:custom-analytics-v1.0.0

# Override the build with your pre-built image
docker compose \
  -f docker-compose.yml \
  -f docker-compose.production.yml \
  -f docker-compose.https.yml \
  up -d
```

---

## 🎯 **What's Included in Your Custom Build**

Your custom CVAT image includes all your modifications:

### **✅ Custom APIs**
- **Frame Download APIs**: Job and Task-based frame export with annotations
- **Analytics APIs**: Time-based analytics, paginated tasks, quick stats
- **Train Metadata APIs**: Complete train management system
- **Task Analysis APIs**: Annotation statistics and breakdowns

### **✅ Database Extensions**
- **TaskTrainMetadata Model**: Extended task model with train-specific fields
- **Custom Migrations**: Database schema for train metadata
- **Optimized Indexes**: Performance improvements for analytics queries

### **✅ UI Integration**
- **React Components**: Train metadata editor integrated into task details
- **CSRF Handling**: Proper security for frontend-backend communication
- **API Integration**: Seamless connection between UI and custom APIs

### **✅ Performance Optimizations**
- **Bulk Database Queries**: Reduced N+1 query problems
- **Parallel Processing**: Multi-threaded frame processing
- **Memory Efficiency**: Optimized for large datasets
- **Caching Ready**: Structured for Redis caching

### **✅ Cross-Platform Features**
- **Font Handling**: Bundled TTF fonts for consistent rendering
- **High-Quality Rendering**: Enhanced annotation drawing with anti-aliasing
- **Production Settings**: Optimized Django configuration

---

## 🔧 **Post-Deployment Setup**

### **1. Initialize Database**
```bash
# Wait for services to start
sleep 30

# Run database migrations
docker compose exec cvat_server python manage.py migrate

# Create superuser
docker compose exec cvat_server python manage.py createsuperuser

# Collect static files
docker compose exec cvat_server python manage.py collectstatic --noinput

# Initialize train metadata for existing tasks
docker compose exec cvat_server python manage.py shell << 'EOF'
from cvat.apps.engine.models import Task
from cvat.apps.custom.models import TaskTrainMetadata

for task in Task.objects.all():
    TaskTrainMetadata.get_or_create_for_task(task)
    print(f"Initialized metadata for task {task.id}")
EOF
```

### **2. Verify Deployment**
```bash
# Check service status
docker compose ps

# Test CVAT API
curl -f https://your-domain.com/api/server/about

# Test Angular Dashboard
curl -f https://your-domain.com/dashboard

# Test Custom Analytics API
curl -H "Authorization: Basic $(echo -n 'admin:password' | base64)" \
     https://your-domain.com/api/custom/train-analytics/
```

---

## 📊 **Service Scaling Commands**

### **Scale Workers for High Load**
```bash
# Scale background workers
docker compose up -d --scale cvat_worker_import=3
docker compose up -d --scale cvat_worker_export=3
docker compose up -d --scale cvat_worker_annotation=4
docker compose up -d --scale cvat_worker_chunks=2
```

### **Resource Monitoring**
```bash
# Monitor resource usage
docker stats

# Check service logs
docker compose logs -f cvat_server
docker compose logs -f angular_dashboard
```

---

## 🔄 **Update Commands**

### **Update CVAT Version**
```bash
# Pull latest images
CVAT_VERSION=v2.44.3 docker compose pull

# Restart with new images
docker compose \
  -f docker-compose.yml \
  -f docker-compose.production.yml \
  -f docker-compose.https.yml \
  up -d

# Run any new migrations
docker compose exec cvat_server python manage.py migrate
```

### **Update Your Custom Code**
```bash
# Pull your latest code
git pull origin main

# Rebuild custom services (if needed)
docker compose build cvat_server

# Restart services
docker compose restart cvat_server angular_dashboard
```

---

## 🛠️ **Maintenance Commands**

### **Backup Database**
```bash
# Create database backup
docker compose exec cvat_db pg_dump -U root cvat > cvat_backup_$(date +%Y%m%d).sql

# Backup volumes
docker run --rm -v cvat_cvat_db_prod:/data -v $(pwd):/backup alpine \
  tar czf /backup/cvat_db_backup_$(date +%Y%m%d).tar.gz -C /data .
```

### **Restore Database**
```bash
# Restore from backup
docker compose exec -T cvat_db psql -U root cvat < cvat_backup_20250910.sql
```

### **Clean Up**
```bash
# Remove unused images and containers
docker system prune -f

# Remove unused volumes (⚠️ DATA LOSS)
docker volume prune -f
```

---

## 🔒 **Security Commands**

### **SSL Certificate Management**
```bash
# Check certificate status
docker compose logs traefik | grep -i certificate

# Force certificate renewal
docker compose exec traefik traefik version
```

### **Firewall Configuration**
```bash
# Configure UFW firewall
sudo ufw enable
sudo ufw allow ssh
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw deny 8080/tcp
sudo ufw deny 5432/tcp
sudo ufw deny 6379/tcp
```

---

## 🏥 **Health Check Commands**

### **Service Health**
```bash
# Check all services
docker compose ps

# Health check endpoints
curl -f https://your-domain.com/api/server/about
curl -f https://your-domain.com/dashboard/health || echo "Dashboard health check not available"

# Database connection test
docker compose exec cvat_server python manage.py dbshell -c "SELECT 1;"

# Redis connection test
docker compose exec cvat_redis_inmem redis-cli ping
docker compose exec cvat_redis_ondisk redis-cli -p 6666 ping
```

### **Performance Monitoring**
```bash
# Database performance
docker compose exec cvat_db psql -U root cvat -c "
SELECT schemaname,tablename,attname,n_distinct,correlation
FROM pg_stats
WHERE schemaname = 'public'
ORDER BY n_distinct DESC LIMIT 10;"

# Redis memory usage
docker compose exec cvat_redis_inmem redis-cli info memory
docker compose exec cvat_redis_ondisk redis-cli -p 6666 info memory
```

---

## 🚨 **Troubleshooting Commands**

### **Common Issues**
```bash
# Services not starting
docker compose logs --tail=50 service_name

# Database connection issues
docker compose exec cvat_server python manage.py check --database default

# SSL certificate issues
docker compose logs traefik | grep -i "certificate\|acme\|error"

# Dashboard not accessible
docker compose exec angular_dashboard wget -qO- http://localhost:8080/health || echo "Dashboard not responding"
```

### **Reset Commands (⚠️ DATA LOSS)**
```bash
# Reset entire deployment
docker compose down -v
docker system prune -f
# Then redeploy from scratch
```

---

## 📈 **Production Optimization Commands**

### **Database Optimization**
```bash
# Analyze database performance
docker compose exec cvat_db psql -U root cvat -c "
SELECT schemaname,tablename,attname,n_distinct,correlation
FROM pg_stats
WHERE schemaname = 'public' AND tablename LIKE '%task%';"

# Vacuum and analyze
docker compose exec cvat_db psql -U root cvat -c "VACUUM ANALYZE;"
```

### **Cache Optimization**
```bash
# Clear Redis cache
docker compose exec cvat_redis_inmem redis-cli FLUSHALL
docker compose exec cvat_redis_ondisk redis-cli -p 6666 FLUSHALL

# Check cache hit rates
docker compose exec cvat_redis_inmem redis-cli info stats | grep keyspace
```

---

## 🎯 **Complete Production Deployment Script**

```bash
#!/bin/bash
# Complete production deployment

set -e

# 1. Set environment variables
export CVAT_HOST=your-domain.com
export CVAT_POSTGRES_PASSWORD=your-secure-password
export ACME_EMAIL=your-email@domain.com
export CVAT_VERSION=v2.44.3

# 2. Create directories
mkdir -p letsencrypt sql
touch letsencrypt/acme.json
chmod 600 letsencrypt/acme.json

# 3. Build custom CVAT image
echo "🏗️ Building custom CVAT image with analytics APIs..."
docker compose \
  -f docker-compose.yml \
  -f docker-compose.production.yml \
  build

# 4. Deploy services
echo "🚀 Deploying CVAT with custom analytics and dashboard..."
docker compose \
  -f docker-compose.yml \
  -f docker-compose.production.yml \
  -f docker-compose.https.yml \
  up -d

# 4. Wait for services
echo "⏳ Waiting for services to start..."
sleep 60

# 5. Initialize database
echo "🗄️ Initializing database..."
docker compose exec cvat_server python manage.py migrate
docker compose exec cvat_server python manage.py collectstatic --noinput

# 6. Verify deployment
echo "🔍 Verifying deployment..."
docker compose ps
curl -f https://$CVAT_HOST/api/server/about || echo "API not ready yet"
curl -f https://$CVAT_HOST/dashboard || echo "Dashboard not ready yet"

echo "✅ Deployment complete!"
echo "🌐 CVAT: https://$CVAT_HOST"
echo "📊 Dashboard: https://$CVAT_HOST/dashboard"
echo "🔧 Create admin user: docker compose exec cvat_server python manage.py createsuperuser"
```

---

## 📚 **References**

- [CVAT Installation Guide](https://docs.cvat.ai/docs/administration/basics/installation/)
- [CVAT HTTPS Deployment](https://docs.cvat.ai/docs/administration/basics/installation/#deploy-secure-cvat-instance-with-https)
- [CVAT External Database](https://docs.cvat.ai/docs/administration/basics/installation/#deploy-cvat-with-an-external-database)
- [Docker Compose Override Files](https://docs.docker.com/compose/extends/)

**Follow these commands for a production-ready CVAT deployment with your custom analytics and Angular dashboard! 🚀**
