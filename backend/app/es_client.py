"""Elasticsearch client + index management for ANPR events.

Search (routers/anpr_search.py) reads from ES; Postgres (AnprEvent) stays
the durable/authoritative store. Kept intentionally small — one index, one
mapping, two helpers.
"""

import logging

from elasticsearch import Elasticsearch

from .config import settings

logger = logging.getLogger("es_client")

_client: Elasticsearch | None = None


def get_client() -> Elasticsearch:
    global _client
    if _client is None:
        _client = Elasticsearch(settings.elasticsearch_url)
    return _client


INDEX_MAPPING = {
    "mappings": {
        "properties": {
            "camera_id": {"type": "keyword"},
            "event_type": {"type": "keyword"},
            "timestamp": {"type": "date"},
            "track_id": {"type": "integer"},
            "vehicle_class": {"type": "keyword"},
            "vehicle_confidence": {"type": "float"},
            "plate_no": {"type": "keyword"},
            "plate_confidence": {"type": "float"},
            # keyword, not integer: consumer_a (Postgres) would have a numeric
            # row id here, but consumer_es (this index's only writer) has no
            # Postgres row to reference and uses a composite string id instead.
            "event_id": {"type": "keyword"},
        }
    }
}


def ensure_index():
    try:
        client = get_client()
        if not client.indices.exists(index=settings.es_index_events):
            client.indices.create(index=settings.es_index_events, body=INDEX_MAPPING)
            logger.info("Created ES index %s", settings.es_index_events)
    except Exception as e:
        # ES may not be up yet at startup — search endpoints will surface
        # errors per-request rather than crashing the whole API on boot.
        logger.warning("Could not ensure ES index (will retry lazily): %s", e)


def index_event(doc_id, event: dict):
    """doc_id is also stored as the event_id field for search-result display —
    it's a Postgres row id when called from consumer_a, or a composite string
    (camera_id-timestamp-seq) when called from consumer_es, which never
    touches Postgres."""
    client = get_client()
    doc = {
        "event_id": doc_id,
        "camera_id": event.get("camera_id"),
        "event_type": event.get("event_type"),
        "timestamp": event.get("timestamp"),
        "track_id": event.get("track_id"),
        "vehicle_class": event.get("vehicle_class"),
        "vehicle_confidence": event.get("vehicle_confidence"),
        "plate_no": event.get("plate_no"),
        "plate_confidence": event.get("plate_confidence"),
    }
    client.index(index=settings.es_index_events, id=str(doc_id), document=doc)


def search_events(
    plate_no: str | None = None,
    camera_id: str | None = None,
    track_id: int | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    camera_ids_scope: list[str] | None = None,
    size: int = 100,
):
    """camera_ids_scope: when provided, restricts results to these camera_ids
    (used to apply department scoping without duplicating that logic in ES)."""
    must = []
    if plate_no:
        must.append({"term": {"plate_no": plate_no.upper()}})
    if camera_id:
        must.append({"term": {"camera_id": camera_id}})
    if track_id is not None:
        must.append({"term": {"track_id": track_id}})
    if start_time or end_time:
        rng = {}
        if start_time:
            rng["gte"] = start_time
        if end_time:
            rng["lte"] = end_time
        must.append({"range": {"timestamp": rng}})
    if camera_ids_scope is not None:
        must.append({"terms": {"camera_id": camera_ids_scope}})

    query = {"bool": {"must": must}} if must else {"match_all": {}}
    client = get_client()
    resp = client.search(
        index=settings.es_index_events,
        query=query,
        sort=[{"timestamp": {"order": "desc"}}],
        size=size,
    )
    return [hit["_source"] for hit in resp["hits"]["hits"]]
