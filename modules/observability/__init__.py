"""Observability module: structured logging to Grafana Loki.

Clean Architecture layers:
- domain: LogEntry entity, LogSender port
- application: LogService use case
- infrastructure: LokiLogSender adapter, log_sender_factory
- interface: logger_factory for agent integration
"""
