import os

# Bind to both 8080 and 10000 (and any PORT env var) so Render's port scanner always finds it
ports = {"8080", "10000"}
port_env = os.environ.get("PORT")
if port_env:
    ports.add(port_env)

bind = [f"0.0.0.0:{p}" for p in sorted(ports)]
workers = 2
threads = 4
timeout = 120
if os.path.exists("/dev/shm"):
    worker_tmp_dir = "/dev/shm"
accesslog = "-"
errorlog = "-"
loglevel = "info"
