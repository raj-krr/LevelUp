import os

port = os.environ.get("PORT", "10000")
bind = f"0.0.0.0:{port}"
workers = 2
threads = 4
timeout = 120
if os.path.exists("/dev/shm"):
    worker_tmp_dir = "/dev/shm"
accesslog = "-"
errorlog = "-"
loglevel = "info"
