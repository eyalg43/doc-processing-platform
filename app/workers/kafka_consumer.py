import json
import logging

from kafka import KafkaConsumer

from app.core.config import settings
from app.workers.tasks import process_document

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_consumer() -> None:
    consumer = KafkaConsumer(
        settings.kafka_topic_documents,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id="doc-workers",
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        value_deserializer=lambda b: json.loads(b.decode("utf-8")),
    )

    logger.info("Kafka consumer started, waiting for messages...")

    for message in consumer:
        event = message.value
        document_id = event.get("document_id")
        tenant_id = event.get("tenant_id")

        logger.info(f"Received event for document_id={document_id}")

        try:
            process_document.delay(document_id, tenant_id)
            consumer.commit()
            logger.info(f"Dispatched Celery task for document_id={document_id}")
        except Exception as e:
            logger.error(f"Failed to dispatch task: {e}")


if __name__ == "__main__":
    run_consumer()
