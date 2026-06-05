# 🚀 Deployment Guide - KishanX Trading Signals

## 📋 Table of Contents
- [Overview](#overview)
- [System Requirements](#system-requirements)
- [Development Setup](#development-setup)
- [Production Deployment](#production-deployment)
- [Docker Deployment](#docker-deployment)
- [Cloud Deployment](#cloud-deployment)
- [Configuration](#configuration)
- [Security Setup](#security-setup)
- [Monitoring & Logging](#monitoring--logging)
- [Backup & Recovery](#backup--recovery)
- [Troubleshooting](#troubleshooting)
- [Maintenance](#maintenance)

## 🎯 Overview

This guide provides comprehensive instructions for deploying the KishanX Trading Signals platform in various environments, from development to production. The platform supports multiple deployment methods including traditional server deployment, Docker containers, and cloud platforms.

### Deployment Options
- **Development**: Local development environment
- **Production**: Traditional server deployment
- **Docker**: Containerized deployment
- **Cloud**: AWS, Azure, Google Cloud deployment
- **Hybrid**: Mixed deployment strategies

## 💻 System Requirements

### Minimum Requirements
- **OS**: Ubuntu 20.04+, CentOS 8+, Windows Server 2019+
- **CPU**: 4 cores, 2.0 GHz
- **RAM**: 8GB (16GB recommended)
- **Storage**: 50GB SSD (100GB recommended)
- **Network**: Stable internet connection (10 Mbps+)

### Recommended Requirements
- **OS**: Ubuntu 22.04 LTS
- **CPU**: 8 cores, 3.0 GHz
- **RAM**: 32GB
- **Storage**: 200GB NVMe SSD
- **Network**: 100 Mbps dedicated connection

### Software Dependencies
- **Python**: 3.8+ (3.9+ recommended)
- **Node.js**: 16+ (for frontend assets)
- **Nginx**: 1.18+ (reverse proxy)
- **PostgreSQL**: 12+ (optional, SQLite default)
- **Redis**: 6+ (optional, for caching)

## 🛠️ Development Setup

### 1. Clone Repository
```bash
git clone <repository-url>
cd KishanX-Trading-Signals
```

### 2. Create Virtual Environment
```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
# Linux/macOS:
source venv/bin/activate
# Windows:
venv\Scripts\activate
```

### 3. Install Dependencies
```bash
# Install Python dependencies
pip install -r requirements.txt

# Install development dependencies (optional)
pip install -r requirements-dev.txt
```

### 4. Environment Configuration
```bash
# Copy environment template
cp .env.example .env

# Edit configuration
nano .env  # Linux/macOS
notepad .env  # Windows
```

### 5. Database Setup
```bash
# Initialize database
python database_setup.py

# Create default admin user
python create_admin_user.py
```

### 6. Run Development Server
```bash
# Run Flask development server
python app.py

# Or use Flask CLI
flask run --host=0.0.0.0 --port=5000
```

### 7. Access Application
- **Main Application**: http://localhost:5000
- **Admin Panel**: http://localhost:5000/admin_panel
- **API Documentation**: http://localhost:5000/api/docs

## 🏭 Production Deployment

### 1. Server Preparation

#### Ubuntu/Debian Setup
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install required packages
sudo apt install python3 python3-pip python3-venv nginx postgresql redis-server -y

# Install additional tools
sudo apt install git curl wget htop tree -y
```

#### CentOS/RHEL Setup
```bash
# Update system
sudo yum update -y

# Install EPEL repository
sudo yum install epel-release -y

# Install required packages
sudo yum install python3 python3-pip nginx postgresql redis -y
```

### 2. Application Setup

#### Create Application User
```bash
# Create application user
sudo useradd -m -s /bin/bash kishanx

# Set password
sudo passwd kishanx

# Add to necessary groups
sudo usermod -aG www-data kishanx
```

#### Deploy Application
```bash
# Switch to application user
sudo su - kishanx

# Create application directory
mkdir -p /home/kishanx/apps
cd /home/kishanx/apps

# Clone repository
git clone <repository-url> kishanx-trading
cd kishanx-trading

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Initialize database
python database_setup.py
```

### 3. Nginx Configuration

#### Create Nginx Configuration
```bash
sudo nano /etc/nginx/sites-available/kishanx-trading
```

#### Nginx Configuration File
```nginx
server {
    listen 80;
    server_name your-domain.com www.your-domain.com;
    
    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "no-referrer-when-downgrade" always;
    add_header Content-Security-Policy "default-src 'self' http: https: data: blob: 'unsafe-inline'" always;
    
    # Static files
    location /static/ {
        alias /home/kishanx/apps/kishanx-trading/static/;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
    
    # Main application
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        
        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
    
    # API endpoints
    location /api/ {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

#### Enable Site
```bash
# Enable site
sudo ln -s /etc/nginx/sites-available/kishanx-trading /etc/nginx/sites-enabled/

# Test configuration
sudo nginx -t

# Restart Nginx
sudo systemctl restart nginx
```

### 4. Systemd Service

#### Create Service File
```bash
sudo nano /etc/systemd/system/kishanx-trading.service
```

#### Service Configuration
```ini
[Unit]
Description=KishanX Trading Signals
After=network.target postgresql.service redis.service

[Service]
Type=simple
User=kishanx
Group=kishanx
WorkingDirectory=/home/kishanx/apps/kishanx-trading
Environment=PATH=/home/kishanx/apps/kishanx-trading/venv/bin
Environment=FLASK_APP=app.py
Environment=FLASK_ENV=production
ExecStart=/home/kishanx/apps/kishanx-trading/venv/bin/python app.py
ExecReload=/bin/kill -s HUP $MAINPID
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

#### Enable and Start Service
```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable service
sudo systemctl enable kishanx-trading

# Start service
sudo systemctl start kishanx-trading

# Check status
sudo systemctl status kishanx-trading
```

### 5. SSL Certificate (Let's Encrypt)

#### Install Certbot
```bash
# Ubuntu/Debian
sudo apt install certbot python3-certbot-nginx -y

# CentOS/RHEL
sudo yum install certbot python3-certbot-nginx -y
```

#### Obtain SSL Certificate
```bash
# Get certificate
sudo certbot --nginx -d your-domain.com -d www.your-domain.com

# Test renewal
sudo certbot renew --dry-run
```

#### Auto-Renewal
```bash
# Add to crontab
sudo crontab -e

# Add this line
0 12 * * * /usr/bin/certbot renew --quiet
```

## 🐳 Docker Deployment

### 1. Dockerfile

#### Create Dockerfile
```dockerfile
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user
RUN useradd -m -u 1000 kishanx && chown -R kishanx:kishanx /app
USER kishanx

# Initialize database
RUN python database_setup.py

# Expose port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# Start application
CMD ["python", "app.py"]
```

### 2. Docker Compose

#### Create docker-compose.yml
```yaml
version: '3.8'

services:
  kishanx-trading:
    build: .
    ports:
      - "5000:5000"
    environment:
      - FLASK_ENV=production
      - DATABASE_URL=sqlite:///data/kishanx.db
      - REDIS_URL=redis://redis:6379/0
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    depends_on:
      - redis
    restart: unless-stopped
    networks:
      - kishanx-network

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis-data:/data
    restart: unless-stopped
    networks:
      - kishanx-network

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./ssl:/etc/nginx/ssl
    depends_on:
      - kishanx-trading
    restart: unless-stopped
    networks:
      - kishanx-network

volumes:
  redis-data:

networks:
  kishanx-network:
    driver: bridge
```

### 3. Nginx Configuration for Docker

#### Create nginx.conf
```nginx
events {
    worker_connections 1024;
}

http {
    upstream kishanx-trading {
        server kishanx-trading:5000;
    }

    server {
        listen 80;
        server_name your-domain.com;

        location / {
            proxy_pass http://kishanx-trading;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
    }
}
```

### 4. Deploy with Docker

#### Build and Run
```bash
# Build and start services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

## ☁️ Cloud Deployment

### AWS Deployment

#### 1. EC2 Instance Setup
```bash
# Launch EC2 instance (Ubuntu 22.04 LTS)
# Instance type: t3.medium or larger
# Security group: Allow HTTP (80), HTTPS (443), SSH (22)

# Connect to instance
ssh -i your-key.pem ubuntu@your-instance-ip
```

#### 2. Application Deployment
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install dependencies
sudo apt install python3 python3-pip python3-venv nginx git -y

# Clone and setup application
git clone <repository-url> kishanx-trading
cd kishanx-trading
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python database_setup.py
```

#### 3. RDS Database (Optional)
```bash
# Create RDS PostgreSQL instance
# Update database configuration in .env
DATABASE_URL=postgresql://username:password@rds-endpoint:5432/kishanx
```

#### 4. S3 Storage (Optional)
```bash
# Create S3 bucket for file storage
# Install AWS CLI
pip install awscli

# Configure AWS credentials
aws configure
```

#### 5. CloudFront CDN (Optional)
```bash
# Create CloudFront distribution
# Point to your EC2 instance
# Configure caching rules for static files
```

### Azure Deployment

#### 1. Azure VM Setup
```bash
# Create Azure VM (Ubuntu 22.04 LTS)
# Size: Standard_B2s or larger
# Configure NSG rules for HTTP, HTTPS, SSH

# Connect to VM
ssh azureuser@your-vm-ip
```

#### 2. Application Deployment
```bash
# Similar to AWS deployment
# Install dependencies and deploy application
```

#### 3. Azure Database (Optional)
```bash
# Create Azure Database for PostgreSQL
# Update connection string
DATABASE_URL=postgresql://username:password@azure-db:5432/kishanx
```

### Google Cloud Deployment

#### 1. Compute Engine Setup
```bash
# Create VM instance (Ubuntu 22.04 LTS)
# Machine type: e2-medium or larger
# Configure firewall rules

# Connect to instance
gcloud compute ssh your-instance --zone=your-zone
```

#### 2. Application Deployment
```bash
# Similar deployment process
# Install dependencies and deploy application
```

## ⚙️ Configuration

### Environment Variables

#### Production Configuration (.env)
```env
# Application Settings
FLASK_ENV=production
SECRET_KEY=your-secret-key-here
DEBUG=False

# Database Configuration
DATABASE_URL=sqlite:///data/kishanx.db
# For PostgreSQL: postgresql://user:pass@localhost:5432/kishanx

# Redis Configuration (Optional)
REDIS_URL=redis://localhost:6379/0

# API Keys
ANGEL_ONE_API_KEY=your-angel-one-key
ANGEL_ONE_CLIENT_ID=your-client-id
ANGEL_ONE_PIN=your-pin
ALPHA_VANTAGE_API_KEY=your-alpha-vantage-key

# Trading Configuration
DEFAULT_BALANCE=100000
MAX_RISK_PER_TRADE=2.0
DEFAULT_STOP_LOSS=1.0
DEFAULT_TAKE_PROFIT=2.0
MAX_CONCURRENT_TRADES=5

# System Configuration
CACHE_DURATION=300
RATE_LIMIT_REQUESTS=100
RATE_LIMIT_WINDOW=3600
SESSION_TIMEOUT=86400

# Email Configuration
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_USE_TLS=True

# Security Configuration
PASSWORD_MIN_LENGTH=8
MAX_LOGIN_ATTEMPTS=5
LOCKOUT_DURATION=900
SESSION_COOKIE_SECURE=True
SESSION_COOKIE_HTTPONLY=True
```

### Database Configuration

#### SQLite (Default)
```python
# No additional configuration needed
# Database file: kishanx.db
```

#### PostgreSQL
```python
# Install PostgreSQL driver
pip install psycopg2-binary

# Update DATABASE_URL
DATABASE_URL=postgresql://user:password@localhost:5432/kishanx
```

#### MySQL
```python
# Install MySQL driver
pip install mysql-connector-python

# Update DATABASE_URL
DATABASE_URL=mysql://user:password@localhost:3306/kishanx
```

### Cache Configuration

#### Redis Cache
```python
# Install Redis
pip install redis

# Configure Redis
REDIS_URL=redis://localhost:6379/0
CACHE_TYPE=redis
```

#### Memory Cache (Default)
```python
# No additional configuration needed
# Uses in-memory caching
```

## 🔒 Security Setup

### SSL/TLS Configuration

#### Let's Encrypt (Recommended)
```bash
# Install Certbot
sudo apt install certbot python3-certbot-nginx -y

# Get certificate
sudo certbot --nginx -d your-domain.com

# Auto-renewal
sudo crontab -e
# Add: 0 12 * * * /usr/bin/certbot renew --quiet
```

#### Custom SSL Certificate
```bash
# Copy certificate files
sudo cp your-cert.crt /etc/ssl/certs/
sudo cp your-key.key /etc/ssl/private/

# Update Nginx configuration
sudo nano /etc/nginx/sites-available/kishanx-trading
```

### Firewall Configuration

#### UFW (Ubuntu)
```bash
# Enable UFW
sudo ufw enable

# Allow SSH
sudo ufw allow ssh

# Allow HTTP/HTTPS
sudo ufw allow 80
sudo ufw allow 443

# Check status
sudo ufw status
```

#### iptables (CentOS)
```bash
# Allow HTTP/HTTPS
sudo iptables -A INPUT -p tcp --dport 80 -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 443 -j ACCEPT

# Save rules
sudo iptables-save > /etc/iptables/rules.v4
```

### Security Headers

#### Nginx Security Headers
```nginx
# Add to server block
add_header X-Frame-Options "SAMEORIGIN" always;
add_header X-XSS-Protection "1; mode=block" always;
add_header X-Content-Type-Options "nosniff" always;
add_header Referrer-Policy "no-referrer-when-downgrade" always;
add_header Content-Security-Policy "default-src 'self' http: https: data: blob: 'unsafe-inline'" always;
```

### Application Security

#### Environment Security
```bash
# Set proper file permissions
chmod 600 .env
chmod 600 kishanx.db
chown kishanx:kishanx .env kishanx.db

# Remove sensitive files
rm -f .env.example
```

## 📊 Monitoring & Logging

### Application Logging

#### Log Configuration
```python
# In app.py
import logging
from logging.handlers import RotatingFileHandler

if not app.debug:
    file_handler = RotatingFileHandler('logs/kishanx.log', maxBytes=10240, backupCount=10)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)
```

#### Log Rotation
```bash
# Create logrotate configuration
sudo nano /etc/logrotate.d/kishanx-trading

# Add configuration
/home/kishanx/apps/kishanx-trading/logs/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 644 kishanx kishanx
}
```

### System Monitoring

#### Install Monitoring Tools
```bash
# Install htop, iotop, nethogs
sudo apt install htop iotop nethogs -y

# Install Prometheus (optional)
wget https://github.com/prometheus/prometheus/releases/download/v2.40.0/prometheus-2.40.0.linux-amd64.tar.gz
tar xvfz prometheus-2.40.0.linux-amd64.tar.gz
```

#### Health Check Endpoint
```python
# Add to app.py
@app.route('/health')
def health_check():
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'version': '1.0.0'
    })
```

### Performance Monitoring

#### Install APM Tools
```bash
# Install New Relic (optional)
pip install newrelic

# Configure New Relic
newrelic-admin generate-config YOUR_LICENSE_KEY newrelic.ini
```

## 💾 Backup & Recovery

### Database Backup

#### Automated Backup Script
```bash
#!/bin/bash
# backup.sh

BACKUP_DIR="/home/kishanx/backups"
DB_FILE="/home/kishanx/apps/kishanx-trading/kishanx.db"
DATE=$(date +%Y%m%d_%H%M%S)

# Create backup directory
mkdir -p $BACKUP_DIR

# Backup database
cp $DB_FILE $BACKUP_DIR/kishanx_$DATE.db

# Compress backup
gzip $BACKUP_DIR/kishanx_$DATE.db

# Remove old backups (keep last 30 days)
find $BACKUP_DIR -name "kishanx_*.db.gz" -mtime +30 -delete

echo "Backup completed: kishanx_$DATE.db.gz"
```

#### Schedule Backup
```bash
# Add to crontab
crontab -e

# Add backup schedule (daily at 2 AM)
0 2 * * * /home/kishanx/backup.sh
```

### File Backup

#### Application Files Backup
```bash
#!/bin/bash
# backup_files.sh

BACKUP_DIR="/home/kishanx/backups"
APP_DIR="/home/kishanx/apps/kishanx-trading"
DATE=$(date +%Y%m%d_%H%M%S)

# Create backup
tar -czf $BACKUP_DIR/kishanx_files_$DATE.tar.gz -C $APP_DIR .

echo "File backup completed: kishanx_files_$DATE.tar.gz"
```

### Recovery Procedures

#### Database Recovery
```bash
# Stop application
sudo systemctl stop kishanx-trading

# Restore database
gunzip -c /home/kishanx/backups/kishanx_20240101_020000.db.gz > kishanx.db

# Set permissions
chown kishanx:kishanx kishanx.db
chmod 600 kishanx.db

# Start application
sudo systemctl start kishanx-trading
```

#### Full System Recovery
```bash
# Restore application files
tar -xzf /home/kishanx/backups/kishanx_files_20240101_020000.tar.gz -C /home/kishanx/apps/kishanx-trading/

# Restore database
gunzip -c /home/kishanx/backups/kishanx_20240101_020000.db.gz > /home/kishanx/apps/kishanx-trading/kishanx.db

# Set permissions
chown -R kishanx:kishanx /home/kishanx/apps/kishanx-trading/
chmod 600 /home/kishanx/apps/kishanx-trading/kishanx.db

# Restart services
sudo systemctl restart kishanx-trading
```

## 🔧 Troubleshooting

### Common Issues

#### Application Won't Start
```bash
# Check service status
sudo systemctl status kishanx-trading

# Check logs
sudo journalctl -u kishanx-trading -f

# Check application logs
tail -f /home/kishanx/apps/kishanx-trading/logs/kishanx.log
```

#### Database Issues
```bash
# Check database file
ls -la kishanx.db

# Check database integrity
sqlite3 kishanx.db "PRAGMA integrity_check;"

# Recreate database
python database_setup.py
```

#### Nginx Issues
```bash
# Check Nginx status
sudo systemctl status nginx

# Test configuration
sudo nginx -t

# Check error logs
sudo tail -f /var/log/nginx/error.log
```

#### Permission Issues
```bash
# Fix ownership
sudo chown -R kishanx:kishanx /home/kishanx/apps/kishanx-trading/

# Fix permissions
chmod 600 kishanx.db .env
chmod 755 /home/kishanx/apps/kishanx-trading/
```

### Performance Issues

#### High CPU Usage
```bash
# Check running processes
htop

# Check system resources
free -h
df -h

# Check application performance
curl -w "@curl-format.txt" -o /dev/null -s "http://localhost:5000/"
```

#### Memory Issues
```bash
# Check memory usage
free -h

# Check swap usage
swapon -s

# Check for memory leaks
ps aux --sort=-%mem | head
```

#### Disk Space Issues
```bash
# Check disk usage
df -h

# Find large files
find /home/kishanx -type f -size +100M

# Clean up logs
sudo journalctl --vacuum-time=7d
```

### Network Issues

#### Connection Problems
```bash
# Check network connectivity
ping google.com

# Check port availability
netstat -tlnp | grep :5000

# Check firewall
sudo ufw status
```

#### SSL Issues
```bash
# Check SSL certificate
openssl x509 -in /etc/ssl/certs/your-cert.crt -text -noout

# Test SSL connection
openssl s_client -connect your-domain.com:443
```

## 🔧 Maintenance

### Regular Maintenance Tasks

#### Daily Tasks
- Check application logs for errors
- Monitor system resources
- Verify backup completion
- Check trading system status

#### Weekly Tasks
- Review performance metrics
- Clean up old log files
- Update system packages
- Test backup recovery

#### Monthly Tasks
- Security updates
- Database optimization
- Performance review
- Capacity planning

### Update Procedures

#### Application Updates
```bash
# Stop application
sudo systemctl stop kishanx-trading

# Backup current version
cp -r /home/kishanx/apps/kishanx-trading /home/kishanx/apps/kishanx-trading.backup

# Pull updates
cd /home/kishanx/apps/kishanx-trading
git pull origin main

# Update dependencies
source venv/bin/activate
pip install -r requirements.txt

# Run database migrations (if any)
python database_migrate.py

# Start application
sudo systemctl start kishanx-trading
```

#### System Updates
```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Restart services
sudo systemctl restart kishanx-trading nginx
```

### Monitoring Setup

#### Install Monitoring Tools
```bash
# Install Prometheus and Grafana
wget https://github.com/prometheus/prometheus/releases/download/v2.40.0/prometheus-2.40.0.linux-amd64.tar.gz
wget https://github.com/grafana/grafana/releases/download/v9.3.0/grafana-9.3.0.linux-amd64.tar.gz
```

#### Configure Alerts
```yaml
# prometheus.yml
rule_files:
  - "kishanx_alerts.yml"

alerting:
  alertmanagers:
    - static_configs:
        - targets:
          - localhost:9093
```

---

**📝 Note**: This deployment guide provides comprehensive instructions for various deployment scenarios. Always test deployments in a staging environment before deploying to production. Keep backups and have a rollback plan ready.
