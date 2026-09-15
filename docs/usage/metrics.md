# Metrics

taskowl exposes Prometheus metrics at `/metrics` on the API server.

```bash
curl http://localhost:8000/metrics
```

```yaml
scrape_configs:
  - job_name: taskowl
    metrics_path: /metrics
    scrape_interval: 15s
    static_configs:
      - targets: ["localhost:8000"]
```

| Metric | Type | Labels |
|--------|------|--------|
| `taskowl_task_events_total` | Counter | `event_type`, `task_name`, `worker` |
| `taskowl_task_execution_duration_seconds` | Histogram | `task_name` |
| `taskowl_worker_status` | Gauge (1 = online, 0 = offline) | `worker` |
| `taskowl_worker_active_tasks` | Gauge | `worker` |
| `taskowl_worker_processed_total` | Counter | `worker` |
| `taskowl_automation_fired_total` | Counter (automation runs that fired actions) | `automation_id`, `trigger` |
| `taskowl_automation_skipped_total` | Counter (runs skipped by a safety mechanism) | `automation_id`, `reason` |

!!! warning
    `/metrics` is intentionally unauthenticated so Prometheus can scrape it
    without the taskowl API key. Only expose it to trusted networks or behind a
    reverse proxy.