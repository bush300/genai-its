"""
Tests for optional Firestore support in the CyberNexa audit logger.

These tests use a mock Firestore client, so they do not connect to the
live Firebase project and do not require service-account credentials.
"""

import json
from unittest.mock import MagicMock

from audit_logger import AuditLogger


def test_injected_firestore_client_enables_firestore(tmp_path):
    mock_client = MagicMock()

    logger = AuditLogger(
        log_file_path=str(tmp_path / "audit_logs.jsonl"),
        firestore_client=mock_client,
    )

    assert logger.firestore_enabled is True
    assert logger.firestore_client is mock_client


def test_event_is_written_to_firestore(tmp_path):
    mock_client = MagicMock()

    logger = AuditLogger(
        log_file_path=str(tmp_path / "audit_logs.jsonl"),
        firestore_client=mock_client,
    )

    event = logger.log_event(
        event_type="contract_violation",
        severity="ERROR",
        user_id="test_student",
        session_id="test_session",
        source_module="ai_gate",
        message="Prompt injection attempt blocked.",
        metadata={
            "attack_type": "prompt_injection",
            "raw_prompt": "Ignore all previous instructions.",
        },
    )

    mock_client.collection.assert_called_once_with("audit_logs")

    document_method = (
        mock_client
        .collection
        .return_value
        .document
    )

    document_method.assert_called_once_with(event.event_id)

    set_method = (
        document_method
        .return_value
        .set
    )

    set_method.assert_called_once()

    saved_data = set_method.call_args.args[0]

    assert saved_data["event_id"] == event.event_id
    assert saved_data["event_type"] == "contract_violation"
    assert saved_data["severity"] == "ERROR"
    assert saved_data["source_module"] == "ai_gate"

    assert logger.last_firestore_write_succeeded is True
    assert logger.last_firestore_error is None


def test_sensitive_metadata_is_redacted_before_firestore_write(tmp_path):
    mock_client = MagicMock()

    logger = AuditLogger(
        log_file_path=str(tmp_path / "audit_logs.jsonl"),
        firestore_client=mock_client,
    )

    logger.log_event(
        event_type="input_sanitisation_flag",
        severity="WARNING",
        message="Unsafe input detected.",
        metadata={
            "raw_prompt": "Sensitive attack prompt",
            "api_key": "secret-key-value",
            "attack_type": "prompt_injection",
        },
    )

    set_method = (
        mock_client
        .collection
        .return_value
        .document
        .return_value
        .set
    )

    saved_data = set_method.call_args.args[0]

    assert saved_data["metadata"]["raw_prompt"] == "[REDACTED]"
    assert saved_data["metadata"]["api_key"] == "[REDACTED]"
    assert saved_data["metadata"]["attack_type"] == "prompt_injection"


def test_local_log_remains_when_firestore_write_fails(tmp_path):
    mock_client = MagicMock()

    set_method = (
        mock_client
        .collection
        .return_value
        .document
        .return_value
        .set
    )

    set_method.side_effect = RuntimeError(
        "Simulated Firestore failure"
    )

    log_path = tmp_path / "audit_logs.jsonl"

    logger = AuditLogger(
        log_file_path=str(log_path),
        firestore_client=mock_client,
    )

    event = logger.log_event(
        event_type="system_error",
        severity="ERROR",
        message="Testing Firestore fallback.",
        metadata={
            "test": True,
        },
    )

    assert logger.last_firestore_write_succeeded is False
    assert "Simulated Firestore failure" in logger.last_firestore_error

    assert log_path.exists()

    log_lines = log_path.read_text(
        encoding="utf-8"
    ).splitlines()

    assert len(log_lines) == 1

    saved_local_event = json.loads(log_lines[0])

    assert saved_local_event["event_id"] == event.event_id
    assert saved_local_event["message"] == (
        "Testing Firestore fallback."
    )


def test_custom_firestore_collection_is_supported(tmp_path):
    mock_client = MagicMock()

    logger = AuditLogger(
        log_file_path=str(tmp_path / "audit_logs.jsonl"),
        firestore_client=mock_client,
        firestore_collection="security_events",
    )

    logger.log_event(
        event_type="rate_limit_hit",
        severity="WARNING",
        message="Rate limit triggered.",
    )

    mock_client.collection.assert_called_once_with(
        "security_events"
    )
