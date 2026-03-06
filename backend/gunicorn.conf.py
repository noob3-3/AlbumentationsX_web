"""
Gunicorn configuration for production deployment
Usage: gunicorn -c gunicorn.conf.py app.main:app
"""
import os
import multiprocessing

# Server socket
bind = f"{os.getenv('HOST', '0.0.0.0')}:{os.getenv('PORT', '8000')}"
backlog = 2048

# Worker processes
workers = int(os.getenv("WORKERS", multiprocessing.cpu_count() * 2 + 1))
worker_class = "uvicorn.workers.UvicornWorker"
worker_connections = 1000
max_requests = 10000
max_requests_jitter = 1000
timeout = 600  # 10 minutes timeout for upload operations
keepalive = 5

# Request size limits (2GB for batch upload)
limit_request_line = 8190
limit_request_fields = 100
limit_request_field_size = 8190

# Logging
accesslog = os.getenv("LOG_DIR", "/app/logs") + "/access.log"
errorlog = os.getenv("LOG_DIR", "/app/logs") + "/error.log"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = "axweb-gunicorn"

# Server mechanics
daemon = False
pidfile = None
umask = 0
user = None
group = None
tmp_upload_dir = None

# SSL (if needed)
# keyfile = None
# certfile = None

# Performance tuning
preload_app = True  # Load application code before worker processes are forked
worker_tmp_dir = "/dev/shm"  # Use RAM disk for worker heartbeat

def on_starting(server):
    """Called just before the master process is initialized."""
    print(f"Starting Gunicorn with {workers} workers on {bind}")

def on_reload(server):
    """Called to recycle workers during a reload."""
    print("Reloading workers...")

def when_ready(server):
    """Called just after the server is started."""
    print(f"Server is ready. Listening on: {bind}")

def worker_int(worker):
    """Called just after a worker exited on SIGINT or SIGQUIT."""
    print(f"Worker {worker.pid} received SIGINT/SIGQUIT")

def worker_abort(worker):
    """Called when a worker received the SIGABRT signal."""
    print(f"Worker {worker.pid} received SIGABRT")

