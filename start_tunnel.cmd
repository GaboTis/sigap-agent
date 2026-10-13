@echo off
"C:\Users\User\Documents\CODE\sigap-agent\tools\cloudflared.exe" tunnel --url http://localhost:8200 --no-autoupdate --loglevel info >> "C:\Users\User\Documents\CODE\sigap-agent\logs\tunnel.log" 2>&1
