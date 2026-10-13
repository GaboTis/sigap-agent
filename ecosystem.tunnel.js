module.exports = {
  apps: [{
    name: 'sigap-tunnel',
    script: 'C:\\Users\\User\\Documents\\CODE\\sigap-agent\\tools\\cloudflared.exe',
    args: 'tunnel --url http://localhost:8200 --no-autoupdate --metrics 127.0.0.1:9111',
    cwd: 'C:\\Users\\User\\Documents\\CODE\\sigap-agent',
    interpreter: 'none',
    instances: 1,
    autorestart: true,
    watch: false,
    max_memory_restart: '300M',
    error_file: './logs/pm2-tunnel-error.log',
    out_file: './logs/pm2-tunnel-out.log',
    log_date_format: 'YYYY-MM-DD HH:mm:ss',
    merge_logs: true,
    min_uptime: '10s',
    max_restarts: 10,
    kill_timeout: 5000
  }]
};
