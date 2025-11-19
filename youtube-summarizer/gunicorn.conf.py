# Gunicorn configuration for Render deployment
import os

bind = f"0.0.0.0:{os.environ.get('PORT', 5000)}"
workers = 1
worker_class = "sync"
worker_connections = 1000
timeout = 300
keepalive = 2
max_requests = 1000
max_requests_jitter = 100
preload_app = True