"""Installed task mappings validate their source records; imported code never runs."""
from .models import Envelope, IntegrityError, ORDERS, PAYMENTS, canonical, validate_structure


def validate_evidence(value) -> Envelope:
    envelope = validate_structure(value)
    if envelope.identity.task_type == ORDERS:
        from .orders import project_orders_facts
        project = project_orders_facts
    elif envelope.identity.task_type == PAYMENTS:
        from .payments import project_payment_facts
        project = project_payment_facts
    else:
        raise IntegrityError("Unsupported task mapping")
    try:
        expected = project(envelope.source_facts)
    except IntegrityError:
        raise
    except (KeyError, TypeError, ValueError, IndexError, RecursionError) as error:
        raise IntegrityError("Task source records are incomplete or inconsistent") from error
    if canonical(expected) != canonical(envelope):
        raise IntegrityError("Incident projection contradicts its preserved source records")
    return envelope
