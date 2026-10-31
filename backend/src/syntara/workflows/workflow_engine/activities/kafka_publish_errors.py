"""Safe Publish failures; delivery certainty is independent of retryability."""

import ssl
from typing import Never

from aiokafka import errors
from temporalio.exceptions import ApplicationError


class KafkaPublishProducerUnavailableError(RuntimeError):
    """A counted producer is retiring or its worker has stopped admission."""

    def __init__(self) -> None:
        """Keep this internal failure free of connection and message data."""
        super().__init__("Kafka producer is unavailable for new sends")


_ERROR_MESSAGES = {
    "kafka_invalid_message": "The Publish message, encoding, or template result is invalid.",
    "kafka_message_too_large": "The message exceeds a Publish or Kafka size limit.",
    "kafka_arguments_too_large": "The encoded Publish arguments exceed the workflow transport limit.",
    "kafka_invalid_reference": "The selected Kafka integration or credential is unavailable for this workflow.",
    "kafka_topic_not_found": "The configured Kafka topic is unavailable.",
    "kafka_authentication_failed": "Kafka rejected the selected runtime credential.",
    "kafka_authorization_failed": "Kafka denied the required operation for the selected runtime identity.",
    "kafka_connection_failed": "The Kafka connection could not be established or was interrupted.",
    "kafka_metadata_unavailable": "Kafka topic or leader metadata is temporarily unavailable.",
    "kafka_capacity_unavailable": "Worker publishing capacity was not available before the deadline.",
    "kafka_timeout": "Kafka delivery was not confirmed before the Publish deadline.",
    "kafka_connection_settings_changed": "Kafka connection settings changed during this Publish invocation.",
    "kafka_producer_failed": "The Kafka producer is unavailable for this send.",
    "kafka_unexpected_error": "Kafka Publish failed unexpectedly.",
}


def publish_failure(code: str, *, uncertain: bool = False, retryable: bool = False) -> ApplicationError:
    """Expose a stable category without broker text, message data, or secrets."""
    status = "unconfirmed" if uncertain else "not_sent"
    message = _ERROR_MESSAGES.get(code, "Kafka Publish failed.")
    if uncertain:
        message += " Delivery was not confirmed; the message may have been published."
    return ApplicationError(
        message,
        {"output": {"error_code": code, "error": message, "delivery_status": status}},
        type=code,
        non_retryable=not retryable,
    )


def fail_publish(code: str, *, uncertain: bool = False, retryable: bool = False) -> Never:
    """Raise a safe failure while discarding sensitive exception context."""
    error = publish_failure(code, uncertain=uncertain, retryable=retryable)
    raise error from None


_ERROR_RULES: tuple[tuple[tuple[type[Exception], ...], str, bool, bool], ...] = (
    ((KafkaPublishProducerUnavailableError,), "kafka_producer_failed", True, False),
    ((errors.AuthenticationFailedError, errors.SaslAuthenticationFailed), "kafka_authentication_failed", False, True),
    (
        (errors.TopicAuthorizationFailedError, errors.ClusterAuthorizationFailedError),
        "kafka_authorization_failed",
        False,
        False,
    ),
    ((errors.MessageSizeTooLargeError, errors.RecordTooLargeError), "kafka_message_too_large", False, False),
    ((errors.InvalidTopicError,), "kafka_topic_not_found", False, False),
    (
        (errors.ProducerFenced, errors.InvalidProducerEpoch, errors.OutOfOrderSequenceNumber),
        "kafka_producer_failed",
        False,
        True,
    ),
    ((errors.ProducerClosed,), "kafka_producer_failed", True, True),
    ((ssl.SSLError,), "kafka_connection_failed", False, True),
    ((TimeoutError, errors.KafkaTimeoutError), "kafka_timeout", True, False),
    ((OSError, errors.KafkaConnectionError), "kafka_connection_failed", True, False),
)


def classify_publish_error(exc: Exception) -> tuple[str, bool, bool]:
    """Return code, retryable, and whether a producer must leave reuse."""
    for types, code, retryable, fatal in _ERROR_RULES:
        if isinstance(exc, types):
            return code, retryable, fatal
    if isinstance(exc, errors.KafkaError) and exc.retriable:
        return "kafka_metadata_unavailable", True, False
    return "kafka_unexpected_error", False, False
