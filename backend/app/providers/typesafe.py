"""Reserved for the sponsor's actual protocol. No network implementation yet."""

from app.config import Settings

STATUS = "not configured — awaiting sponsor instructions"


def configuration_status(settings: Settings) -> str:
    # Placeholder values do not establish an endpoint or authentication protocol.
    return STATUS
