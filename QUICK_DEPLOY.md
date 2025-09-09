# 🚀 Quick Deployment Guide - CVAT with Analytics Dashboard

## ⚡ **One-Command Deployment**

```bash
# Clone, configure, and deploy in one go
git clone https://github.com/your-username/cvat.git
cd cvat
./deploy.sh
```

---

## 🎯 **Essential Steps**

### **1. Server Prerequisites**
```bash
# Install Docker & Docker Compose
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# Logout and login again
```

### **2. Quick Configuration**
```bash
# Copy and edit environment
cp env.production.example .env
nano .env  # Edit CVAT_HOST, passwords, email
```

### **3. Deploy Services**
```bash
# Automated deployment
./deploy.sh

# Manual deployment (alternative)
docker-compose -f docker-compose.yml -f docker-compose.production.yml up -d
```

### **4. Initialize System**
```bash
# Create admin user
docker-compose exec cvat_server python manage.py createsuperuser

# Verify deployment
curl http://localhost/api/server/about
curl http://localhost/dashboard
```

---

## 🌐 **Access Points**

| Service | URL | Description |
|---------|-----|-------------|
| **CVAT Main** | `http://your-domain.com/` | Main annotation interface |
| **Dashboard** | `http://your-domain.com/dashboard` | Analytics dashboard |
| **API Docs** | `http://your-domain.com/api/docs` | API documentation |
| **Analytics** | `http://your-domain.com/api/custom/` | Custom analytics APIs |

---

## 📊 **Dashboard Integration**

Your Angular dashboard (`ghcr.io/prabaljainn/orochi-ui:latest`) is automatically integrated with:

### **Available API Endpoints**
```javascript
// Analytics data
GET /api/custom/train-analytics/
GET /api/custom/tasks-paginated/
GET /api/custom/tasks-quick-stats/

// Task analysis
GET /api/custom/task-analysis/{task_id}/

// Train metadata
GET /api/custom/train-metadata-list/
```

### **Authentication**
```javascript
// Use CVAT session or basic auth
const headers = {
    'Authorization': 'Basic ' + btoa('username:password'),
    'Content-Type': 'application/json'
};
```

---

## 🔧 **Configuration Files**

### **Key Files Created**
- `docker-compose.production.yml` - Production services
- `deploy.sh` - Automated deployment script
- `env.production.example` - Environment template
- `DEPLOYMENT_GUIDE.md` - Detailed deployment guide

### **Environment Variables**
```bash
# Essential settings
CVAT_HOST=your-domain.com
CVAT_POSTGRES_PASSWORD=secure-password
CVAT_ANALYTICS_ENABLED=true
ANGULAR_DASHBOARD_ENABLED=true
```

---

## 🏥 **Health Checks**

```bash
# Service status
docker-compose ps

# API health
curl http://localhost/api/server/about

# Dashboard health
curl http://localhost/dashboard

# Analytics API
curl -H "Authorization: Basic $(echo -n 'admin:password' | base64)" \
     http://localhost/api/custom/train-analytics/
```

---

## 🛠️ **Common Commands**

```bash
# View logs
docker-compose logs -f cvat_server
docker-compose logs -f angular_dashboard

# Restart services
docker-compose restart

# Update system
git pull
docker-compose pull
docker-compose up -d

# Backup database
docker-compose exec cvat_db pg_dump -U root cvat > backup.sql

# Scale services (if needed)
docker-compose up -d --scale cvat_worker=3
```

---

## 🔒 **Security Checklist**

- [ ] Change default passwords in `.env`
- [ ] Configure SSL certificates
- [ ] Set up firewall (ports 80, 443 only)
- [ ] Enable automatic security updates
- [ ] Configure backup strategy
- [ ] Set up monitoring/alerting

---

## 🚨 **Troubleshooting**

### **Services won't start**
```bash
docker-compose logs
docker system prune -f
docker-compose up -d
```

### **Dashboard can't connect to API**
```bash
# Check CORS configuration
docker-compose exec cvat_server python manage.py shell
>>> from django.conf import settings
>>> print(settings.CORS_ORIGIN_WHITELIST)
```

### **Database issues**
```bash
# Reset database (⚠️ DATA LOSS)
docker-compose down -v
docker-compose up -d
```

---

## 📞 **Support**

- **Documentation**: `./DEPLOYMENT_GUIDE.md`
- **System Overview**: `./CVAT_CUSTOM_SYSTEM_COMPLETE.md`
- **Logs**: `docker-compose logs [service_name]`
- **Health**: `curl http://localhost/api/server/about`

---

## 🎉 **Success Indicators**

✅ **All services running**: `docker-compose ps` shows all "Up"
✅ **CVAT accessible**: Can login at `http://your-domain.com`
✅ **Dashboard working**: Analytics visible at `/dashboard`
✅ **APIs responding**: Custom endpoints return data
✅ **SSL configured**: HTTPS redirects working

**You're ready to start annotating and analyzing! 🚀**
