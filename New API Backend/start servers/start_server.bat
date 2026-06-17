@echo off
echo Starting Advanced AI Python Server...
:: Starts the python server in the background
start /b uvicorn advanced_ai_api:app --host 0.0.0.0 --port 8000

echo Starting Ngrok Secure Tunnel...
:: Starts the tunnel linking your laptop to the public internet
ngrok http --domain=taste-retreat-anvil.ngrok-free.dev 8000