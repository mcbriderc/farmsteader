import multiprocessing

bind = "unix:/run/farmsteader/gunicorn.sock"
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "gthread"
threads = 2
timeout = 120
accesslog = "-"
errorlog = "-"
loglevel = "info"
