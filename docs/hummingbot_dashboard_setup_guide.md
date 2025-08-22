# Hummingbot Dashboard Setup Guide

## 🐳 **Step 1: Enable Docker Desktop WSL2 Integration**

You have Docker Desktop installed on Windows, but it needs to be configured for WSL2 integration.

### **Enable WSL2 Integration:**

1. **Open Docker Desktop** on Windows
2. **Go to Settings** (gear icon in top right)
3. **Navigate to Resources → WSL Integration**
4. **Enable WSL Integration**
   - Turn on "Enable integration with my default WSL distro"
   - Turn on integration for your specific Ubuntu distro
5. **Click "Apply & Restart"**

### **Alternative: Install Docker directly in WSL2**

If Docker Desktop integration doesn't work, install Docker directly:

```bash
# Update package index
sudo apt update

# Install required packages
sudo apt install -y apt-transport-https ca-certificates curl gnupg lsb-release

# Add Docker's official GPG key
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg

# Add Docker repository
echo "deb [arch=amd64 signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Update package index again
sudo apt update

# Install Docker Engine
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Add user to docker group
sudo usermod -aG docker $USER

# Start Docker service
sudo service docker start

# Verify installation
docker --version
docker-compose --version
```

## 🚀 **Step 2: Clone Hummingbot Dashboard Repository**

Once Docker is working, clone the Dashboard deployment repository:

```bash
# Navigate to home directory
cd /home/thien

# Clone the Deploy repository
git clone https://github.com/hummingbot/deploy
cd deploy

# Check contents
ls -la
```

## ⚙️ **Step 3: Configure Dashboard for Somnia**

### **Modify docker-compose.yml for Custom Connector**

The Dashboard needs to recognize your custom Somnia connector. We'll need to:

1. **Map your custom Hummingbot directory** to the Dashboard container
2. **Configure connector settings** for Somnia
3. **Set up proper volumes** for configuration persistence

### **Create Custom Configuration**

```bash
# Create custom config directory
mkdir -p /home/thien/deploy/custom-configs

# Copy your Somnia connector files
cp -r /home/thien/hummingbot/hummingbot/connector/exchange/somnia /home/thien/deploy/custom-configs/

# Copy your arbitrage configurations
cp /home/thien/hummingbot/conf/strategies/*.yml /home/thien/deploy/custom-configs/
```

## 🎯 **Step 4: Launch Dashboard**

```bash
# Navigate to deploy directory
cd /home/thien/deploy

# Run the setup script
bash setup.sh

# Wait for containers to start
# Then access Dashboard at: http://localhost:8501
```

## 🔧 **Step 5: Configure Dashboard for Arbitrage**

### **Add Somnia Credentials**

1. **Open Dashboard** at http://localhost:8501
2. **Go to Credentials** section
3. **Add Somnia exchange** credentials:
   - Connector: Custom (Somnia)
   - Private Key: Your wallet private key
   - RPC URL: Somnia RPC endpoint

### **Create Arbitrage Strategy**

1. **Go to Config Generator**
2. **Select AMM Arbitrage** strategy
3. **Configure pairs**:
   - Market 1: STT-USDC
   - Market 2: WBTC-USDC (or SOL-USDC)
4. **Set parameters**:
   - Order Amount: 10.0
   - Min Profitability: 0.5%
   - Slippage Buffer: 1.0%

### **Backtest Strategy**

1. **Set date range** for backtesting
2. **Run backtest** to validate strategy
3. **Adjust parameters** based on results
4. **Upload configuration** when satisfied

### **Deploy Bot**

1. **Go to Deploy V2** section
2. **Select your arbitrage config**
3. **Give instance a name** (e.g., "somnia-stt-wbtc-arb")
4. **Launch Bot**

## 📊 **Step 6: Monitor Performance**

### **Dashboard Features**

- **Portfolio View**: Monitor STT, USDC, WBTC, SOL balances
- **Instance Management**: Start/stop arbitrage bots
- **Performance Metrics**: Track profits, volume, success rate
- **Logs**: Real-time log monitoring
- **Multiple Strategies**: Run different arbitrage pairs simultaneously

### **Key Metrics to Watch**

- Net PNL (Profit/Loss)
- Volume Traded
- Number of Arbitrage Opportunities
- Success Rate
- Average Profit per Trade

## 🚨 **Troubleshooting**

### **Common Issues**

1. **Docker not accessible**: Enable WSL2 integration in Docker Desktop
2. **Port conflicts**: Ensure ports 8501, 8000 are not in use
3. **Connector not recognized**: Map custom Hummingbot directory properly
4. **Configuration errors**: Validate YAML syntax and connector settings

### **Custom Connector Integration**

If Dashboard doesn't recognize Somnia connector:

1. **Create connector mapping** in Dashboard configuration
2. **Add Somnia to certified exchanges** list
3. **Modify connector detection** logic

## 📝 **Next Steps After Setup**

1. **Test with small amounts** initially
2. **Monitor closely** for first few hours
3. **Adjust parameters** based on performance
4. **Scale up** gradually
5. **Add more arbitrage pairs** (STT-SOL, WBTC-SOL)

## 🎯 **Benefits of Dashboard Approach**

- ✅ **Visual Interface**: Easier than CLI configuration
- ✅ **Multi-Strategy**: Run multiple arbitrage bots
- ✅ **Real-time Monitoring**: Web-based portfolio tracking
- ✅ **Backtesting**: Test strategies before live deployment
- ✅ **Remote Access**: Monitor from anywhere
- ✅ **Performance Analytics**: Detailed trading metrics

---

**First, let's get Docker working properly, then we can proceed with the Dashboard setup!**
