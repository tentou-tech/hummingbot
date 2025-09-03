# Hummingbot Dashboard Setup

This repository has been successfully built as a Docker image and configured for use with the Hummingbot Dashboard.

## 🚀 Quick Start

### Option 1: Dashboard + Hummingbot (Recommended)

```bash
# Start services with just dashboard (no API)
docker-compose -f docker-compose.dashboard-simple.yml up -d

# Check status
docker-compose -f docker-compose.dashboard-simple.yml ps
```

### Option 2: Full setup with API

```bash
# Start all services including API (requires database setup)
docker-compose -f docker-compose.dashboard.yml up -d

# Check status
docker-compose -f docker-compose.dashboard.yml ps
```

### Using the startup script

```bash
./start-dashboard
```

## 📊 Access Points

- **Hummingbot Dashboard**: http://localhost:8501
- **Hummingbot API** (if enabled): http://localhost:8080

## 🔧 Management Commands

```bash
# View logs
docker-compose -f docker-compose.dashboard.yml logs -f

# Stop services
docker-compose -f docker-compose.dashboard.yml down

# Access Hummingbot CLI directly
docker exec -it hummingbot bash

# Restart services
docker-compose -f docker-compose.dashboard.yml restart
```

## 📁 Data Persistence

All important data is persisted in local directories:

- `./conf/` - Configuration files
- `./logs/` - Log files
- `./data/` - Database and state files
- `./certs/` - SSL certificates
- `./scripts/` - Custom scripts

## 🏗️ Built Images

- **Main Image**: `hummingbot-hummingbot:latest` (4.42GB)
- **Tagged As**: `hummingbot/hummingbot:latest`
- **Dashboard**: `hummingbot/dashboard:latest`

## 📖 Documentation

For more detailed setup instructions, visit:

- [Hummingbot Docker Installation](https://hummingbot.org/installation/docker/#install-docker-compose)
- [Hummingbot Dashboard Documentation](https://hummingbot.org/dashboard/)

## 🐛 Troubleshooting

### Check service logs

```bash
docker-compose -f docker-compose.dashboard.yml logs hummingbot
docker-compose -f docker-compose.dashboard.yml logs dashboard
```

### API Connection Issues

If the API container fails to start due to database connection errors:

```bash
# Use the simplified setup without API
docker-compose -f docker-compose.dashboard.yml down
docker-compose -f docker-compose.dashboard-simple.yml up -d
```

### Rebuild the image

```bash
docker-compose build --no-cache
```

### Reset everything

```bash
docker-compose -f docker-compose.dashboard.yml down
docker system prune -f
./start-dashboard
```
