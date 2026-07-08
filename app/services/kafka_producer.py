import json
import uuid

from kafka import KafkaProducer
from kafka.errors import NoBrokersAvailable

from app.core.config import settings

_producer = None


def get_producer() -> KafkaProducer | None:
    global _producer
    if _producer is None:
        try:
            _producer = KafkaProducer(
                bootstrap_servers=settings.kafka_bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            )
        except NoBrokersAvailable:
            return None
    return _producer


def publish_document_event(document_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    producer = get_producer()
    if producer is None:
        # Kafka unavailable — fall back to direct Celery dispatch
        from app.workers.tasks import process_document
        process_document.delay(str(document_id), str(tenant_id))
        return
    producer.send(
        settings.kafka_topic_documents,
        value={
            "document_id": str(document_id),
            "tenant_id": str(tenant_id),
        },
    )
    producer.flush()
