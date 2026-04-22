#!/bin/bash
# NAS Dashboard Deployment Script
# Run this on your NAS terminal (SSH to victor@alexnas or via Docker)

set -e

NAS_DIR="/var/services/homes/Victor/nas-dashboard"
PORT=5004

echo "=== NAS Dashboard Deployment ==="

# Step 1: Create directory
mkdir -p "$NAS_DIR"
cd "$NAS_DIR"

# Step 2: Build Docker image
echo "Building Docker image..."
docker compose build

# Step 3: Start container
echo "Starting container..."
docker compose up -d

# Step 4: Wait and check health
sleep 5
echo "Checking health..."
curl -s http://127.0.0.1:$PORT/health && echo ""

echo ""
echo "=== Deployment Complete ==="
echo "Dashboard: http://100.102.165.11:$PORT"
echo "Pages:"
echo "  http://100.102.165.11:$PORT/summary"
echo "  http://100.102.165.11:$PORT/sales"
echo "  http://100.102.165.11:$PORT/polymarket"
