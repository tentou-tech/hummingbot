# Hummingbot Dashboard Setup

This repository has been successfully built as a Docker image and configured for use with the Hummingbot Dashboard.

## 🚀 Quick Start

### Using the startup script (Recommended)

```bash
./start-dashboard
```

### Manual setup

```bash
# Start services
docker-compose -f docker-compose.dashboard.yml up -d

# Check status
docker-compose -f docker-compose.dashboard.yml ps
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
