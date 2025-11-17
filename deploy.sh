#!/bin/bash
# Deployment script for Media Sorter
# Usage: ./deploy.sh [user@]hostname

set -e

if [ -z "$1" ]; then
    echo "Usage: ./deploy.sh [user@]hostname"
    echo "Example: ./deploy.sh user@192.168.0.30"
    exit 1
fi

HOST="$1"
REMOTE_DIR="/opt/media-sorter"

echo "Deploying Media Sorter to $HOST"
echo "================================"

# Clone from GitHub on remote server
echo "Step 1: Installing git and cloning repository..."
ssh "$HOST" "sudo apt-get update && sudo apt-get install -y git"
ssh "$HOST" "sudo rm -rf $REMOTE_DIR && sudo git clone https://github.com/ruhitrafian66/media-sorter.git $REMOTE_DIR"

# Run installation
echo "Step 2: Running installation script..."
ssh "$HOST" "cd $REMOTE_DIR && sudo bash install.sh"

# Configure service
echo "Step 3: Configuring service..."
echo "Please edit the service file on the remote server:"
echo "  ssh $HOST"
echo "  sudo nano /etc/systemd/system/media-sorter.service"
echo ""
echo "Then start the service:"
echo "  sudo systemctl daemon-reload"
echo "  sudo systemctl enable media-sorter"
echo "  sudo systemctl start media-sorter"
echo "  sudo systemctl status media-sorter"
echo ""
echo "Deployment complete!"
