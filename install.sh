#!/bin/bash
# Installation script for Media Sorter

set -e

echo "Media Sorter Installation"
echo "========================="

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run as root (use sudo)"
    exit 1
fi

# Install Python dependencies
echo "Installing Python dependencies..."
apt-get update
apt-get install -y python3 python3-pip
pip3 install -r requirements.txt

# Create installation directory
INSTALL_DIR="/opt/media-sorter"
echo "Creating installation directory: $INSTALL_DIR"
mkdir -p $INSTALL_DIR
cp media_sorter.py $INSTALL_DIR/
chmod +x $INSTALL_DIR/media_sorter.py

# Create media directories (customize these paths)
echo "Creating media directories..."
mkdir -p /media/incoming
mkdir -p /media/TV
mkdir -p /media/Movies

# Install systemd service
echo "Installing systemd service..."
cp media-sorter.service /etc/systemd/system/
echo "Please edit /etc/systemd/system/media-sorter.service to set your username and paths"

echo ""
echo "Installation complete!"
echo ""
echo "Next steps:"
echo "1. Edit /etc/systemd/system/media-sorter.service with your settings"
echo "2. (Optional) Get a free TMDB API key from https://www.themoviedb.org/settings/api"
echo "3. Enable the service: sudo systemctl enable media-sorter"
echo "4. Start the service: sudo systemctl start media-sorter"
echo "5. Check status: sudo systemctl status media-sorter"
echo "6. View logs: sudo journalctl -u media-sorter -f"
