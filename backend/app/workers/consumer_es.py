"""Consumer B — standalone process (own docker-compose service, reusing the
backend image with `command: python -m app.workers.consumer_es`). Indexes
every ANPR event into Elasticsearch. Separate from Consumer A because it
doesn't need access to in-process WebSocket connections.

Run: python -m app.workers.consumer_es
"""

import asyncio
import json
import logging

from aiokafka import AIOKafkaConsumer

from ..config import settings
from ..es_client import ensure_index, index_event

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("consumer_es")

# Monotonically-increasing local id, since this process doesn't share
# Postgres row ids with Consumer A — ES documents here are keyed by
# camera_id+timestamp instead so re-indexing is idempotent-ish.
_seq = 0


async def run():
    global _seq
    ensure_index()
    backoff = 2
    while True:
        consumer = AIOKafkaConsumer(
            settings.anpr_kafka_topic,
            bootstrap_servers=settings.kafka_bootstrap_servers,
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
            group_id="model2-consumer-es",
            auto_offset_reset="latest",
        )
        try:
            await consumer.start()
            logger.info("Consumer ES connected to Kafka, consuming '%s'", settings.anpr_kafka_topic)
            backoff = 2
            async for msg in consumer:
                try:
                    _seq += 1
                    doc_id = f"{msg.value.get('camera_id')}-{msg.value.get('timestamp')}-{_seq}"
                    index_event(doc_id, msg.value)
                except Exception as e:
                    logger.exception("Consumer ES failed to index event: %s", e)
        except Exception as e:
            logger.warning("Consumer ES Kafka connection failed (%s); retrying in %ss", e, backoff)
        finally:
            await consumer.stop()
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 30)


if __name__ == "__main__":
    asyncio.run(run())
