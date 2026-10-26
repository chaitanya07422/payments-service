module.exports = {
  apps: [
    {
      name: "payments-service",
      cwd: "/home/ubuntu/apps/payments-service",
      script: ".venv/bin/payments-service",
      interpreter: "none",
      env: {
        NODE_ENV: "production",
      },
      max_memory_restart: "200M",
      error_file: "/home/ubuntu/apps/payments-service/logs/err.log",
      out_file: "/home/ubuntu/apps/payments-service/logs/out.log",
    },
  ],
};
