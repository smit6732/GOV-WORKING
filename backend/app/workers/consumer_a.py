"""Consumer A — runs *inside* the FastAPI backend process as a background
asyncio task (started from main.py's startup event), because it needs to
push alerts to WebSocket connections that live in this same process's
memory. Per Kafka message (ANPR_Standalone's vehicle_detection /
plate_only_detection event, unchanged): insert AnprEvent, check the plate
against active TaggedPlates, on a match insert AnprAlert + audit log + push
over /ws/alerts.

Consumer B (Elasticsearch indexing) is a separate process — see
consumer_es.py — since it doesn't need access to those WebSocket objects.
"""

import asyncio
import datetime
import json
import logging

from aiokafka import AIOKafkaConsumer

from .. import models
from ..config import settings
from ..database import SessionLocal
from ..utils import normalize_plate, write_audit_log
from ..ws_manager import manager as ws_manager

logger = logging.getLogger("consumer_a")

_task: asyncio.Task | None = None


def _parse_timestamp(raw) -> datetime.datetime:
    if isinstance(raw, str):
        try:
            return datetime.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.datetime.utcnow()


async def _handle_event(db_session_factory, event: dict):
    db = db_session_factory()
    try:
        row = models.AnprEvent(
            camera_id=event.get("camera_id", "unknown"),
            event_type=event.get("event_type", "vehicle_detection"),
            timestamp=_parse_timestamp(event.get("timestamp")),
            track_id=event.get("track_id"),
            vehicle_class=event.get("vehicle_class"),
            vehicle_bbox=json.dumps(event["vehicle_bbox"]) if event.get("vehicle_bbox") else None,
            vehicle_confidence=event.get("vehicle_confidence"),
            plate_no=normalize_plate(event.get("plate_no")),
            plate_confidence=event.get("plate_confidence"),
            plate_bbox=json.dumps(event["plate_bbox"]) if event.get("plate_bbox") else None,
        )
        db.add(row)
        db.commit()
        db.refresh(row)

        if not row.plate_no:
            return row, None

        camera = db.query(models.Camera).filter(models.Camera.camera_id == row.camera_id).first()
        camera_department = camera.department if camera else None

        tag = (
            db.query(models.TaggedPlate)
            .filter(models.TaggedPlate.plate_no == row.plate_no)
            .filter(models.TaggedPlate.is_active.is_(True))
            .filter(
                (models.TaggedPlate.department.is_(None))
                | (models.TaggedPlate.department == camera_department)
            )
            .first()
        )
        if not tag:
            return row, None

        alert = models.AnprAlert(
            event_id=row.id,
            camera_id=row.camera_id,
            tagged_plate_id=tag.id,
            plate_no=row.plate_no,
            matched_reason=tag.reason,
        )
        db.add(alert)
        db.commit()
        db.refresh(alert)

        write_audit_log(
            db, None, "alert_triggered", "tagged_plate", str(tag.id),
            {"plate_no": row.plate_no, "camera_id": row.camera_id, "event_id": row.id},
        )
        return row, {
            "alert_id": alert.id,
            "plate_no": row.plate_no,
            "camera_id": row.camera_id,
            "district": camera.district if camera else None,
            "department": camera_department,
            "matched_reason": tag.reason,
            "timestamp": row.timestamp.isoformat(),
        }
    finally:
        db.close()


async def _run():
    backoff = 2
    while True:
        consumer = AIOKafkaConsumer(
            settings.anpr_kafka_topic,
            bootstrap_servers=settings.kafka_bootstrap_servers,
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
            group_id="model2-consumer-a",
            auto_offset_reset="latest",
        )
        try:
            await consumer.start()
            logger.info("Consumer A connected to Kafka, consuming '%s'", settings.anpr_kafka_topic)
            backoff = 2
            async for msg in consumer:
                try:
                    _, alert_payload = await _handle_event(SessionLocal, msg.value)
                    if alert_payload:
                        await ws_manager.broadcast(
                            {"type": "alert", **alert_payload}, alert_payload.get("department")
                        )
                except Exception as e:
                    logger.exception("Consumer A failed to process event: %s", e)
        except Exception as e:
            logger.warning("Consumer A Kafka connection failed (%s); retrying in %ss", e, backoff)
        finally:
            await consumer.stop()
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 30)


def start():
    global _task
    if _task is None or _task.done():
        _task = asyncio.create_task(_run())


def stop():
    if _task is not None:
        _task.cancel()
