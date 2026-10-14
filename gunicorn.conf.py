import os

# Bind dynamically to the port provided by Render (defaults to 10000)
port = os.environ.get("PORT", "10000")
bind = f"0.0.0.0:{port}"

# Single worker with multi-threading to stay well within Render Free Tier memory (512MB)
workers = 1
threads = 4
timeout = 120
keepalive = 5

# Stream logs directly to Render console
accesslog = "-"
errorlog = "-"
loglevel = "info"
