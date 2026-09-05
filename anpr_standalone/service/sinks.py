"""
Pluggable output sinks for ANPR events.

The Model 2 architecture note calls for Kafka + Elasticsearch +
Postgres downstream. This module doesn't hard-depend on any of them —
it defines a tiny interface (`emit(event: dict)`) and ships two
working sinks (console, JSONL file) plus a commented-out Kafka sink
you can enable once a broker is available.
"""

import json
import threading
from datetime import datetime


class ConsoleSink:
    """Prints each event as one JSON line. Good for quick demos."""

    def emit(self, event: dict) -> None:
        print(json.dumps(event, default=str))


class JSONLFileSink:
    """
    Appends each event as one JSON line to a file. Stands in for a
    durable queue during local development — every event that would
    go to Kafka lands here instead, in the same shape.
    """

    def __init__(self, path: str = "anpr_events.jsonl"):
        self.path = path
        self._lock = threading.Lock()

    def emit(self, event: dict) -> None:
        line = json.dumps(event, default=str)
        with self._lock:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line + "\n")


class MultiSink:
    """Fan a single event out to several sinks at once."""

    def __init__(self, *sinks):
        self.sinks = sinks

    def emit(self, event: dict) -> None:
        for sink in self.sinks:
            sink.emit(event)


# ---------------------------------------------------------------------
# Kafka sink — enabled for Model 2 (`pip install kafka-python`, already
# in requirements.txt). Topic layout:
#   topic: "anpr.vehicle-events"
#   key:   camera_id (keeps per-camera ordering)
#   value: the event dict, JSON-encoded
# ---------------------------------------------------------------------

from kafka import KafkaProducer


class KafkaSink:
    def __init__(self, bootstrap_servers: str, topic: str = "anpr.vehicle-events"):
        self.topic = topic
        self.producer = KafkaProducer(
            bootstrap_servers=bootstrap_servers,
            value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8"),
        )

    def emit(self, event: dict) -> None:
        self.producer.send(self.topic, key=event["camera_id"], value=event)
