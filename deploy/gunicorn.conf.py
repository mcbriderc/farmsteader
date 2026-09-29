"""Gunicorn configuration, driven entirely by environment variables.

Every value has a safe default and an env override, so the same file serves the
systemd install (socket bind, sized by the installer) and the container image
(TCP bind, sized by the operator).

The worker default is the reason this file exists. The stock
`cpu_count() * 2 + 1` reads the *host's* CPU count inside an LXC unless lxcfs
masks /proc/cpuinfo: on a 16-core Proxmox node that is 33 workers at ~130 MB
each -- over 4 GB -- in a container that usually has 2. It is capped at 4 here,
and the installer writes GUNICORN_WORKERS from the machine's RAM anyway.
"""

import multiprocessing
import os


def _int(name, default):
    value = os.environ.get(name, "").strip()
    return int(value) if value else default


_cpu = multiprocessing.cpu_count()

bind = os.environ.get("GUNICORN_BIND", "unix:/run/farmsteader/gunicorn.sock")
workers = _int("GUNICORN_WORKERS", _int("WEB_CONCURRENCY", max(2, min(_cpu * 2 + 1, 4))))
# gthread, because several views call external APIs (weather, soil, prices)
# synchronously and spend their time blocked on the network, not the CPU.
worker_class = "gthread"
threads = _int("GUNICORN_THREADS", 4)
timeout = _int("GUNICORN_TIMEOUT", 120)
graceful_timeout = 30
# Recycle workers periodically so slow leaks (GDAL, pandas via yfinance) cannot
# grow without bound. The jitter stops every worker restarting at once.
max_requests = 1000
max_requests_jitter = 100

accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")
