"""Gunicorn configuration for DigitalOcean App Platform."""
import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8080')}"
workers = 2
threads = 4
timeout = 120
worker_tmp_dir = "/dev/shm"
accesslog = "-"
errorlog = "-"
loglevel = "info"

