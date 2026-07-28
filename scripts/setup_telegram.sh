#!/bin/bash
# Setup Telegram Chat ID and restart bot

CHAT_ID="1050966161"
SERVER="root@95.81.101.148"

echo "Updating Telegram Chat ID on server..."

ssh $SERVER << ENDSSH
cd /opt/claude-ml-trading

# Update Chat ID in .env file
sed -i "s/TELEGRAM_CHAT_ID=.*/TELEGRAM_CHAT_ID=$CHAT_ID/" .env

# Verify the change
echo "Updated .env:"
grep TELEGRAM_CHAT_ID .env

# Restart containers
echo ""
echo "Restarting Docker containers..."
docker-compose down
docker-compose up -d

# Wait for startup
echo "Waiting 10 seconds for services to start..."
sleep 10

# Check status
echo ""
echo "Container status:"
docker-compose ps

echo ""
echo "✅ Telegram bot configured with Chat ID: $CHAT_ID"
echo "Now send /start to your bot in Telegram to test!"
ENDSSH
