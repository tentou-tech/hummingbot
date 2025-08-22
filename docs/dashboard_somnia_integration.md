# Custom Docker Compose for Hummingbot Dashboard with Somnia Connector

## The Challenge

You have a **custom Hummingbot build** with a **Somnia connector**, but the Dashboard uses standard Hummingbot Docker images that don't include your custom connector.

## Solutions

### 🔧 **Option 1: Mount Custom Hummingbot Source (Quick)**

Create a custom docker-compose file that mounts your Hummingbot source:

```yaml
# /home/thien/deploy/custom-docker-compose.yml
services:
  dashboard:
    container_name: dashboard
    image: hummingbot/dashboard:latest
    ports:
      - "8501:8501"
    environment:
      - AUTH_SYSTEM_ENABLED=False
      - BACKEND_API_HOST=hummingbot-api
      - BACKEND_API_PORT=8000
      - BACKEND_API_USERNAME=1
      - BACKEND_API_PASSWORD=1
    volumes:
      - ./credentials.yml:/home/dashboard/credentials.yml
      - ./pages:/home/dashboard/frontend/pages
    networks:
      - emqx-bridge

  hummingbot-api:
    container_name: hummingbot-api
    image: hummingbot/hummingbot-api:latest
    ports:
      - "8000:8000"
    volumes:
      - ./bots:/hummingbot-api/bots
      - /var/run/docker.sock:/var/run/docker.sock
      # Mount your custom Hummingbot source
      - /home/thien/hummingbot:/hummingbot-api/hummingbot
    env_file:
      - .env
    environment:
      - BROKER_HOST=emqx
      - DATABASE_URL=postgresql+asyncpg://hbot:hummingbot-api@postgres:5432/hummingbot_api
      # Add Python path for custom connector
      - PYTHONPATH=/hummingbot-api:/hummingbot-api/hummingbot
    networks:
      - emqx-bridge
    depends_on:
      - postgres

  # ... rest of services (emqx, postgres) remain the same
```

### 🏗️ **Option 2: Build Custom API Image (Best)**

1. **Create Dockerfile for custom API:**

```dockerfile
# /home/thien/hummingbot/Dockerfile.api
FROM hummingbot/hummingbot-api:latest

# Copy your custom Hummingbot source
COPY . /hummingbot-api/hummingbot

# Install any additional dependencies for Somnia
RUN pip install standardweb3

# Set Python path
ENV PYTHONPATH=/hummingbot-api:/hummingbot-api/hummingbot

WORKDIR /hummingbot-api
```

2. **Update docker-compose to build locally:**

```yaml
hummingbot-api:
  build:
    context: /home/thien/hummingbot
    dockerfile: Dockerfile.api
  # ... rest of configuration
```

### 🔍 **Option 3: Hybrid Approach (Current)**

Keep using the current setup but add Somnia connector recognition:

1. **Add connector mapping to Dashboard:**

```bash
# Copy connector files to Dashboard
cp -r /home/thien/hummingbot/hummingbot/connector/exchange/somnia /home/thien/deploy/bots/connectors/
cp -r /home/thien/hummingbot/hummingbot/connector/gateway/somnia /home/thien/deploy/bots/connectors/
```

2. **Update Dashboard connector list:**

```python
# In Dashboard configuration
SUPPORTED_CONNECTORS = [
    "binance",
    "coinbase_pro",
    "kucoin",
    "somnia",  # Add your custom connector
    # ... other connectors
]
```

## 🚀 **Quick Implementation Steps**

### Step 1: Test Current Setup

```bash
# Check if Somnia connector is recognized
docker exec -it hummingbot-api python -c "from hummingbot.connector.exchange.somnia.somnia_exchange import SomniaExchange; print('Somnia connector found!')"
```

### Step 2: If not recognized, use mount approach:

```bash
# Stop current services
cd /home/thien/deploy
docker-compose down

# Create custom compose file with mounts
# Then restart with custom configuration
docker-compose -f custom-docker-compose.yml up -d
```

### Step 3: Verify Somnia connector in Dashboard

1. Access Dashboard at http://localhost:8501
2. Go to "Create Strategy" or "Add Connector"
3. Check if "Somnia" appears in the connector list
4. If yes, configure with your credentials:
   - Private Key: Your wallet private key
   - RPC URL: Somnia testnet/mainnet RPC
   - Chain ID: Somnia chain ID

## 🔧 **Troubleshooting**

### If Somnia connector not visible:

1. **Check logs:** `docker logs hummingbot-api`
2. **Verify mount:** `docker exec -it hummingbot-api ls -la /hummingbot-api/hummingbot/connector/exchange/`
3. **Check imports:** Test connector import inside container

### If strategies don't run:

1. **Check permissions:** Ensure mounted files are readable
2. **Check dependencies:** Verify standardweb3 is installed in container
3. **Check configuration:** Ensure Somnia credentials are properly set

## 🎯 **Expected Result**

After implementation:

- ✅ Somnia connector visible in Dashboard
- ✅ Arbitrage strategies can be configured through web UI
- ✅ Real-time monitoring of Somnia trades
- ✅ Backtesting with Somnia data
- ✅ Multi-strategy deployment for STT/USDC, WBTC/USDC, SOL/USDC pairs

Would you like me to help implement Option 1 (mount approach) first to test it quickly?
