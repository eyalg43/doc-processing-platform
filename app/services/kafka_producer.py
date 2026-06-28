import json
import uuid

from kafka import KafkaProducer

from app.core.config import settings

_producer = None


def get_producer() -> KafkaProducer:
    global _producer
    if _producer is None:
        _producer = KafkaProducer(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        )
    return _producer


def publish_document_event(document_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    producer = get_producer()
    producer.send(
        settings.kafka_topic_documents,
        value={
            "document_id": str(document_id),
            "tenant_id": str(tenant_id),
        },
    )
    producer.flush()
