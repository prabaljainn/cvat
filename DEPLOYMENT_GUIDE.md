# 🚀 CVAT Custom System - Production Deployment Guide

## 📋 **Prerequisites**

### **Server Requirements**
- **OS**: Ubuntu 20.04+ / CentOS 7+ / RHEL 8+
- **CPU**: 4+ cores (8+ recommended)
- **RAM**: 8GB minimum (16GB+ recommended)
- **Storage**: 100GB+ SSD
- **Network**: Public IP with ports 80, 443 open

### **Software Requirements**
- **Docker**: 20.10+
- **Docker Compose**: 2.0+
- **Git**: Latest version
- **SSL Certificate**: For HTTPS (Let's Encrypt recommended)

---

## 🛠️ **Step-by-Step Deployment**

### **Step 1: Server Setup**

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Logout and login to apply docker group
exit
# SSH back in
```

### **Step 2: Clone and Setup CVAT**

```bash
# Clone your CVAT repository
git clone https://github.com/your-username/cvat.git
cd cvat

# Create environment file
cp .env.example .env

# Edit environment variables
nano .env
```

### **Step 3: Configure Environment Variables**

```bash
# .env file configuration
CVAT_HOST=your-domain.com
CVAT_POSTGRES_PASSWORD=your-secure-password-here
CVAT_REDIS_PASSWORD=your-redis-password-here

# SSL Configuration (if using Let's Encrypt)
ACME_EMAIL=your-email@domain.com
TRAEFIK_CERTIFICATESRESOLVERS_LETSENCRYPT_ACME_EMAIL=your-email@domain.com

# Analytics Configuration
CVAT_ANALYTICS_ENABLED=true
CVAT_CUSTOM_FEATURES_ENABLED=true

# Dashboard Configuration
ANGULAR_DASHBOARD_ENABLED=true
```

### **Step 4: Database Initialization**

```bash
# Create SQL initialization script
mkdir -p sql
cat > sql/init-analytics.sql << 'EOF'
-- Initialize analytics extensions
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Create indexes for analytics performance
CREATE INDEX IF NOT EXISTS idx_task_created_date ON engine_task(created_date);
CREATE INDEX IF NOT EXISTS idx_task_updated_date ON engine_task(updated_date);
CREATE INDEX IF NOT EXISTS idx_train_metadata_verdict ON custom_tasktrainmetadata(verdict);
CREATE INDEX IF NOT EXISTS idx_train_metadata_created ON custom_tasktrainmetadata(created_date);

-- Analytics views for better performance
CREATE OR REPLACE VIEW analytics_task_summary AS
SELECT
    t.id,
    t.name,
    t.created_date,
    t.updated_date,
    t.status,
    p.name as project_name,
    tm.verdict,
    tm.train_id,
    tm.confidence_score
FROM engine_task t
LEFT JOIN engine_project p ON t.project_id = p.id
LEFT JOIN custom_tasktrainmetadata tm ON t.id = tm.task_id;
EOF
```

### **Step 5: SSL Certificate Setup (Let's Encrypt)**

```bash
# Create Traefik configuration
mkdir -p traefik
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
      email: your-email@domain.com
      storage: /letsencrypt/acme.json
      httpChallenge:
        entryPoint: web

providers:
  docker:
    exposedByDefault: false
EOF

# Create acme.json with correct permissions
mkdir -p letsencrypt
touch letsencrypt/acme.json
chmod 600 letsencrypt/acme.json
```

### **Step 6: Deploy the System**

```bash
# Build and start services
docker-compose -f docker-compose.yml -f docker-compose.production.yml up -d

# Wait for services to start (2-3 minutes)
docker-compose logs -f cvat_server

# Check if all services are running
docker-compose ps
```

### **Step 7: Initialize CVAT Database**

```bash
# Run database migrations
docker-compose exec cvat_server python manage.py migrate

# Create superuser
docker-compose exec cvat_server python manage.py createsuperuser

# Collect static files
docker-compose exec cvat_server python manage.py collectstatic --noinput

# Create initial train metadata for existing tasks
docker-compose exec cvat_server python manage.py shell << 'EOF'
from cvat.apps.engine.models import Task
from cvat.apps.custom.models import TaskTrainMetadata

for task in Task.objects.all():
    TaskTrainMetadata.get_or_create_for_task(task)
    print(f"Created metadata for task {task.id}")
EOF
```

### **Step 8: Verify Deployment**

```bash
# Check service health
curl -f http://your-domain.com/api/server/about || echo "CVAT API not ready"
curl -f http://your-domain.com/dashboard || echo "Dashboard not ready"

# Test custom APIs
curl -H "Authorization: Basic $(echo -n 'admin:password' | base64)" \
     http://your-domain.com/api/custom/train-analytics/

# Check logs for any errors
docker-compose logs cvat_server | tail -50
docker-compose logs angular_dashboard | tail -50
```

---

## 🔧 **Configuration Files**

### **Production Docker Compose Override**

The `docker-compose.production.yml` includes:
- **Angular Dashboard Integration**
- **Production Database Configuration**
- **Redis Caching Setup**
- **Traefik SSL Termination**
- **CORS Configuration for Dashboard**

### **Nginx Configuration (Alternative to Traefik)**

If you prefer Nginx over Traefik:

```bash
# Create nginx configuration
cat > nginx/cvat.conf << 'EOF'
upstream cvat_server {
    server cvat_server:8080;
}

upstream angular_dashboard {
    server angular_dashboard:8080;
}

server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /etc/ssl/certs/your-domain.com.crt;
    ssl_certificate_key /etc/ssl/private/your-domain.com.key;

    # Dashboard routes
    location /dashboard {
        proxy_pass http://angular_dashboard;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location ~ ^/(en|ar|ja)/ {
        proxy_pass http://angular_dashboard;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # CVAT API and UI
    location /api {
        proxy_pass http://cvat_server;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # CORS headers for dashboard
        add_header Access-Control-Allow-Origin *;
        add_header Access-Control-Allow-Methods "GET, POST, PUT, PATCH, DELETE, OPTIONS";
        add_header Access-Control-Allow-Headers "Content-Type, Authorization, X-CSRFToken";
    }

    location / {
        proxy_pass http://cvat_server;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF
```

---

## 📊 **Dashboard Integration**

### **API Endpoints for Dashboard**

Your Angular dashboard can now access these CVAT analytics APIs:

```typescript
// Dashboard API integration
const CVAT_API_BASE = 'https://your-domain.com/api/custom';

// Get analytics data
const analytics = await fetch(`${CVAT_API_BASE}/train-analytics/?from_time=2025-01-01T00:00:00Z`);

// Get paginated tasks
const tasks = await fetch(`${CVAT_API_BASE}/tasks-paginated/?page=1&page_size=20`);

// Get quick stats for widgets
const stats = await fetch(`${CVAT_API_BASE}/tasks-quick-stats/`);
```

### **Authentication Integration**

```typescript
// Use CVAT session authentication
const authHeaders = {
    'Authorization': 'Basic ' + btoa('username:password'),
    'Content-Type': 'application/json',
    'X-CSRFToken': getCsrfToken() // Get from CVAT cookies
};
```

---

## 🔒 **Security Configuration**

### **Firewall Setup**

```bash
# Configure UFW firewall
sudo ufw enable
sudo ufw allow ssh
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw deny 8080/tcp  # Block direct access to services
sudo ufw deny 5432/tcp  # Block direct database access
```

### **SSL Security Headers**

Add to your web server configuration:

```nginx
# Security headers
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
add_header X-Frame-Options "SAMEORIGIN" always;
add_header X-Content-Type-Options "nosniff" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline';" always;
```

---

## 📈 **Performance Optimization**

### **Database Optimization**

```sql
-- Add to your PostgreSQL configuration
# postgresql.conf
shared_buffers = 256MB
effective_cache_size = 1GB
maintenance_work_mem = 64MB
checkpoint_completion_target = 0.9
wal_buffers = 16MB
default_statistics_target = 100
random_page_cost = 1.1
effective_io_concurrency = 200
```

### **Redis Configuration**

```bash
# redis.conf optimizations
maxmemory 512mb
maxmemory-policy allkeys-lru
save 900 1
save 300 10
save 60 10000
```

---

## 🔍 **Monitoring & Logging**

### **Health Check Endpoints**

```bash
# Add health checks to your monitoring
curl -f https://your-domain.com/api/server/about
curl -f https://your-domain.com/dashboard/health
curl -f https://your-domain.com/api/custom/tasks-quick-stats/
```

### **Log Aggregation**

```bash
# Centralized logging with ELK stack
docker-compose logs -f | grep -E "(ERROR|WARN|CRITICAL)"

# Rotate logs
echo '{"log-driver":"json-file","log-opts":{"max-size":"10m","max-file":"3"}}' | sudo tee /etc/docker/daemon.json
sudo systemctl restart docker
```

---

## 🚀 **Deployment Commands Summary**

```bash
# Complete deployment in one script
#!/bin/bash
set -e

echo "🚀 Deploying CVAT with Custom Analytics & Dashboard..."

# 1. Clone and setup
git clone https://github.com/your-username/cvat.git
cd cvat

# 2. Environment setup
cp .env.example .env
# Edit .env with your values

# 3. Deploy services
docker-compose -f docker-compose.yml -f docker-compose.production.yml up -d

# 4. Wait for services
sleep 60

# 5. Initialize database
docker-compose exec cvat_server python manage.py migrate
docker-compose exec cvat_server python manage.py collectstatic --noinput

# 6. Verify deployment
curl -f http://localhost/api/server/about
curl -f http://localhost/dashboard

echo "✅ Deployment complete!"
echo "🌐 CVAT: https://your-domain.com"
echo "📊 Dashboard: https://your-domain.com/dashboard"
echo "🔧 Admin: Create superuser with 'docker-compose exec cvat_server python manage.py createsuperuser'"
```

---

## 🎯 **Post-Deployment Checklist**

### ✅ **Verify Services**
- [ ] CVAT UI accessible at `https://your-domain.com`
- [ ] Angular Dashboard accessible at `https://your-domain.com/dashboard`
- [ ] API endpoints responding at `https://your-domain.com/api`
- [ ] Custom analytics APIs working
- [ ] SSL certificates valid and auto-renewing

### ✅ **Test Integration**
- [ ] Dashboard can fetch CVAT analytics data
- [ ] Train metadata system working in CVAT UI
- [ ] Frame download APIs functional
- [ ] Authentication working between services

### ✅ **Performance Check**
- [ ] Database queries optimized
- [ ] Redis caching active
- [ ] Static files served efficiently
- [ ] Response times under 2 seconds

### ✅ **Security Verification**
- [ ] HTTPS enforced
- [ ] Firewall configured
- [ ] Database not publicly accessible
- [ ] CORS properly configured

---

## 🆘 **Troubleshooting**

### **Common Issues**

```bash
# Service not starting
docker-compose logs service_name

# Database connection issues
docker-compose exec cvat_server python manage.py dbshell

# Permission issues
sudo chown -R $USER:$USER .
chmod +x scripts/*.sh

# SSL certificate issues
docker-compose logs traefik
```

### **Rollback Procedure**

```bash
# Quick rollback
docker-compose down
git checkout previous-working-commit
docker-compose up -d
```

---

## 🎉 **Success!**

Your CVAT system with custom analytics and Angular dashboard is now deployed and ready for production use!

**Access Points:**
- **CVAT Main**: `https://your-domain.com`
- **Analytics Dashboard**: `https://your-domain.com/dashboard`
- **API Documentation**: `https://your-domain.com/api/docs`
- **Custom Analytics**: `https://your-domain.com/api/custom/`

**Next Steps:**
1. Create admin user and configure projects
2. Import your data and start annotating
3. Use the dashboard for analytics and reporting
4. Monitor system performance and scale as needed
