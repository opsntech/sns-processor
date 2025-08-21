# SNS Event Processor

A lightweight Python service that consumes AWS SNS events (like SES bounces/deliveries), 
stores them locally in S3, and optionally forwards a summary via email.

## Features
- Receive SNS events (via HTTP/Flask)
- Persist to local log files
- Upload events to S3 (partitioned by `year/month/day`)
- Send email notifications (SES or SMTP)
- Docker + Docker Compose ready

## Quick Start

1. Clone the repo:
   ```bash
   git clone https://github.com/opsntech/sns-processor.git
   cd sns-processor

2. Copy .env.example to .env and update values.

3. Build & run:
   ```bash
    docker-compose up --build
   
5. Expose the service endpoint to SNS:
   ```bash
    Create an SNS subscription with protocol = HTTP/HTTPS
    Point to http://<host>:8000/sns

## Roadmap
- Metrics dashboard (Grafana/Prometheus)
- Athena/QuickSight integration
- Configurable retention policy
