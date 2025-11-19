#!/bin/bash

# YouTube Summarizer Deployment Script

set -e

echo "🚀 Starting YouTube Summarizer deployment..."

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

# Check if nvidia-docker is available (for GPU support)
if docker run --rm --gpus all nvidia/cuda:11.8-base-ubuntu22.04 nvidia-smi &> /dev/null; then
    echo "✅ GPU support detected"
    USE_GPU=true
else
    echo "⚠️  No GPU support detected, using CPU mode"
    USE_GPU=false
fi

# Create necessary directories
mkdir -p outputs uploads static/images

# Copy environment file if it doesn't exist
if [ ! -f .env ]; then
    cp .env.example .env
    echo "📝 Created .env file. Please edit it with your configuration."
fi

# Build and start the application
echo "🔨 Building Docker image..."
docker-compose build

echo "🚀 Starting services..."
if [ "$USE_GPU" = true ]; then
    docker-compose up -d
else
    # Use CPU-only version
    docker-compose -f docker-compose.yml -f docker-compose.cpu.yml up -d
fi

# Wait for services to start
echo "⏳ Waiting for services to start..."
sleep 10

# Check if services are running
if docker-compose ps | grep -q "Up"; then
    echo "✅ Services are running!"
    echo "🌐 Application is available at: http://localhost:5000"
    echo "📊 To view logs: docker-compose logs -f"
    echo "🛑 To stop: docker-compose down"
else
    echo "❌ Services failed to start. Check logs with: docker-compose logs"
    exit 1
fi

echo "🎉 Deployment completed successfully!"