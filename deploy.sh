#!/bin/bash
# ============================================================================
# Claude ML Trading System - Automated Deployment Script
# ============================================================================
# This script automates the complete deployment process to a remote server.
# Usage: ./deploy.sh [server_user@server_host]
# ============================================================================

set -e  # Exit on error

# Configuration
SERVER="${1:-root@95.81.101.148}"
PROJECT_DIR="/opt/claude-ml-trading"
GIT_BRANCH="main"
CONTAINER_NAME="claude-ml-bot"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔══════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  Claude ML Trading System - Deployer    ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════╝${NC}"
echo ""

# Function to print status
print_status() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

print_info() {
    echo -e "${BLUE}[→]${NC} $1"
}

# Check if git is configured
print_info "Checking git configuration..."
if ! git config user.name &>/dev/null; then
    print_warning "Git user.name not set. Setting up..."
    git config user.name "Claude ML Bot"
    git config user.email "bot@claude-ml.local"
fi

# Check if remote is configured
print_info "Checking git remote..."
if ! git remote | grep -q origin; then
    print_warning "No git remote configured."
    read -p "Enter your Git repository URL (or press Enter to skip): " GIT_URL
    if [ -n "$GIT_URL" ]; then
        git remote add origin "$GIT_URL"
        print_status "Git remote added: $GIT_URL"
    else
        print_warning "Skipping git remote setup. You'll need to configure it manually."
    fi
fi

# Commit and push changes
print_info "Committing local changes..."
git add .
if git diff --cached --quiet; then
    print_warning "No changes to commit."
else
    git commit -m "Auto-deploy: $(date '+%Y-%m-%d %H:%M:%S')"

    # Push to remote
    print_info "Pushing to repository..."
    if git push origin "$GIT_BRANCH" 2>/dev/null; then
        print_status "Code pushed successfully"
    else
        print_warning "Push failed. Continuing with local deployment..."
    fi
fi

# Remote deployment
print_info "Deploying to server: $SERVER"
echo ""

# Step 1: Copy files to server
print_info "Uploading project files to server..."
rsync -avz --exclude='.git' --exclude='.venv' --exclude='__pycache__' \
    --exclude='node_modules' --exclude='.pytest_cache' \
    ./ "$SERVER:$PROJECT_DIR/"

# Step 2: SSH into server and execute commands
print_info "Executing deployment commands on server..."
ssh "$SERVER" << ENDSSH
set -e

echo "[Server] Navigating to project directory..."
cd $PROJECT_DIR

echo "[Server] Installing/updating Docker if needed..."
if ! command -v docker &>/dev/null; then
    curl -fsSL https://get.docker.com | sh
    usermod -aG docker \$USER || true
fi

echo "[Server] Building and starting containers..."
docker-compose down || true
docker-compose build --no-cache
docker-compose up -d

echo "[Server] Waiting for services to start..."
sleep 5

echo "[Server] Checking container status..."
docker ps -a | grep claude-ml

echo "[Server] Viewing recent logs..."
docker-compose logs --tail=20 claude-ml-trading

echo "[Server] Deployment complete!"
ENDSSH

print_status "Deployment to $SERVER completed!"
echo ""
print_info "Useful commands:"
echo "   View logs:     ssh $SERVER 'cd $PROJECT_DIR && docker-compose logs -f'"
echo "   Stop service:  ssh $SERVER 'cd $PROJECT_DIR && docker-compose down'"
echo "   Restart:       ssh $SERVER 'cd $PROJECT_DIR && docker-compose restart'"
echo "   Status:        ssh $SERVER 'cd $PROJECT_DIR && docker-compose ps'"
