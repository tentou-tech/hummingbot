# How to Deploy Somnia Arbitrage Through Dashboard

## 🎯 **Step-by-Step Deployment Guide**

### **Step 1: Access Dashboard**

1. Open browser to: http://localhost:8501
2. Login with credentials:
   - Username: `1`
   - Password: `1`

### **Step 2: Add Somnia Connector Credentials**

1. Click **"Credentials"** in sidebar
2. Click **"Add Connector"**
3. Select **"Somnia"** from dropdown (if available)
4. Fill in your credentials:
   ```
   Private Key: 0x2dc62809b2f0de83a43b8acdede7a9e696d435b94287561200a12c3e903d626b
   RPC URL: https://dream-rpc.somnia.network
   Chain ID: 50312
   Wallet Address: 0xa3d3bf1DCCB0C53887fF94822BF197fB7Eb961D8
   ```
5. Click **"Save"**

### **Step 3: Create Bot Instance**

1. Go to **"Deploy"** → **"Create"**
2. Configure bot:
   - **Bot Name**: `somnia-stt-wbtc-arb`
   - **Image**: Select `hummingbot/hummingbot:somnia` (your custom image)
   - **Strategy**: Upload or select `stt_amm_arb_config.yml`

### **Step 4: Deploy Strategy**

1. Click **"Create Bot"**
2. Wait for container to start
3. Click **"Start"** to begin trading

### **Step 5: Monitor Performance**

1. Go to **"Dashboard"** tab
2. Monitor:
   - Portfolio balance
   - Active orders
   - P&L performance
   - Trade history

## 🔧 **Alternative: Manual Docker Deployment**

If Dashboard deployment doesn't work, deploy manually:

```bash
# Deploy STT-WBTC arbitrage bot
docker run -d \
  --name somnia-stt-wbtc-arb \
  --network deploy_emqx-bridge \
  -v /home/thien/deploy/bots/configs/stt_amm_arb_config.yml:/conf/conf_client.yml \
  -e BROKER_HOST=emqx \
  hummingbot/hummingbot:somnia

# Check bot status
docker logs somnia-stt-wbtc-arb

# Deploy additional arbitrage bots
docker run -d \
  --name somnia-stt-sol-arb \
  --network deploy_emqx-bridge \
  -v /home/thien/deploy/bots/configs/stt_sol_arb_config.yml:/conf/conf_client.yml \
  -e BROKER_HOST=emqx \
  hummingbot/hummingbot:somnia

docker run -d \
  --name somnia-wbtc-sol-arb \
  --network deploy_emqx-bridge \
  -v /home/thien/deploy/bots/configs/wbtc_sol_arb_config.yml:/conf/conf_client.yml \
  -e BROKER_HOST=emqx \
  hummingbot/hummingbot:somnia
```

## 📊 **Monitoring Commands**

```bash
# Check all deployed bots
docker ps | grep somnia

# View bot logs
docker logs -f somnia-stt-wbtc-arb

# Stop a bot
docker stop somnia-stt-wbtc-arb

# Restart a bot
docker restart somnia-stt-wbtc-arb
```

## 🚨 **Important Notes**

1. **Test with Small Amounts**: Start with minimal trading amounts
2. **Monitor Closely**: Watch the first few trades carefully
3. **Check Balances**: Ensure sufficient STT, WBTC, SOL, and USDC
4. **Network Fees**: Monitor gas costs on Somnia network
5. **Slippage**: Adjust spread parameters if needed

## 🎯 **Expected Results**

Once deployed successfully:

- ✅ Bots appear in Dashboard "Deploy" section
- ✅ Real-time portfolio tracking
- ✅ Trade notifications via EMQX
- ✅ Historical performance data
- ✅ P&L calculations across all pairs

## 🔄 **Next Steps After Deployment**

1. **Monitor Performance**: Check Dashboard metrics
2. **Adjust Parameters**: Modify spread/amounts if needed
3. **Scale Up**: Increase trading amounts gradually
4. **Add Pairs**: Deploy additional arbitrage opportunities

# Dashboard Deployment Guide

## Steps to Deploy Your Somnia Arbitrage Bots:

### 1. Access Dashboard

- Open: http://localhost:8501
- Login: username `1`, password `1`

### 2. Create New Bot Instance

- Click "Deploy" or "Create Bot"
- Select Image: `hummingbot/hummingbot:somnia` (your custom image)
- Choose Strategy: Load one of your arbitrage configs

### 3. Configure Bot

- **Bot Name**: e.g., "somnia-stt-wbtc-arb"
- **Strategy File**: Upload `stt_amm_arb_config.yml`
- **Credentials**: Your Somnia private key and RPC settings

### 4. Start Trading

- Deploy the bot
- Monitor performance in real-time
- View trades, profits, and errors

## Your Available Strategies:

1. **STT/USDC vs WBTC/USDC**: Cross-pair arbitrage
2. **STT/USDC vs SOL/USDC**: Cross-pair arbitrage
3. **WBTC/USDC vs SOL/USDC**: Cross-pair arbitrage

## Benefits of Dashboard Deployment:

- ✅ Visual monitoring
- ✅ Easy bot management
- ✅ Performance analytics
- ✅ Multiple strategies simultaneously
- ✅ Web-based control panel
