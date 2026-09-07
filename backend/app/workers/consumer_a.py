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

# How long a given (camera_id, track_id) pair is treated as "the same
# vehicle pass" for dedup purposes. ByteTrack ids are only unique within
# one continuous stream/session and get reused as the count wraps over a
# long-running process, so this window keeps a stale, long-ago id from
# being confused with a brand-new vehicle that happens to reuse the number.
TRACK_DEDUP_WINDOW = datetime.timedelta(minutes=3)


def _better_plate_reading(existing_conf, existing_plate, new_conf, new_plate) -> bool:
    """True if the new reading should replace what's stored: a plate read
    where there was none before, or a higher-confidence read of one."""
    if not existing_plate:
        return bool(new_plate)
    if not new_plate:
        return False
    return (new_conf or 0) > (existing_conf or 0)


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
        camera_id = event.get("camera_id", "unknown")
        track_id = event.get("track_id")
        timestamp = _parse_timestamp(event.get("timestamp"))
        new_plate_no = normalize_plate(event.get("plate_no"))
        new_plate_conf = event.get("plate_confidence")

        # Dedup only applies to tracked vehicle detections — plate_only_detection
        # events never carry a track_id, so there's no vehicle pass to
        # associate them with; each inserts its own row as before.
        existing = None
        if track_id is not None:
            existing = (
                db.query(models.AnprEvent)
                .filter(models.AnprEvent.camera_id == camera_id)
                .filter(models.AnprEvent.track_id == track_id)
                .filter(models.AnprEvent.timestamp >= timestamp - TRACK_DEDUP_WINDOW)
                .order_by(models.AnprEvent.timestamp.desc())
                .first()
            )

        is_new_row = existing is None
        if existing is not None:
            # Same vehicle pass already has a row — overwrite it with a
            # strictly better plate reading instead of inserting a new row
            # per frame this vehicle appears in (was: one row per frame).
            row = existing
            if _better_plate_reading(row.plate_confidence, row.plate_no, new_plate_conf, new_plate_no):
                row.plate_no = new_plate_no
                row.plate_confidence = new_plate_conf
                if event.get("plate_bbox"):
                    row.plate_bbox = json.dumps(event["plate_bbox"])
            if event.get("vehicle_confidence") is not None:
                row.vehicle_confidence = event["vehicle_confidence"]
            if event.get("vehicle_bbox"):
                row.vehicle_bbox = json.dumps(event["vehicle_bbox"])
            row.timestamp = timestamp
        else:
            row = models.AnprEvent(
                camera_id=camera_id,
                event_type=event.get("event_type", "vehicle_detection"),
                timestamp=timestamp,
                track_id=track_id,
                vehicle_class=event.get("vehicle_class"),
                vehicle_bbox=json.dumps(event["vehicle_bbox"]) if event.get("vehicle_bbox") else None,
                vehicle_confidence=event.get("vehicle_confidence"),
                plate_no=new_plate_no,
                plate_confidence=new_plate_conf,
                plate_bbox=json.dumps(event["plate_bbox"]) if event.get("plate_bbox") else None,
            )
            db.add(row)

        db.commit()
        db.refresh(row)

        if not row.plate_no:
            return row, None

        # Don't re-alert on every later frame of a vehicle pass this row
        # already produced an alert for.
        if not is_new_row and db.query(models.AnprAlert).filter(models.AnprAlert.event_id == row.id).first():
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
