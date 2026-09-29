"""Local service checks and safe failure metadata; never contact model providers."""
from __future__ import annotations

import traceback
from pathlib import Path

import httpx

from app.adapters.business_tools import WorldClient
from app.config import ConfigurationError


class ServiceNotReady(RuntimeError):
    pass


async def simulator_readiness(settings):
    """Verify schema and control access without creating a world or effect."""
    client = None
    try:
        client = WorldClient(settings.faultlab_simulator_url, settings.local_control_token())
        response = await client.control('GET', '/control/ready')
        if response != {'status': 'ok', 'service': 'faultlab-simulator', 'schema_version': 'faultlab/v1'}:
            return {'ready': False, 'code': 'SIMULATOR_VERSION_MISMATCH',
                    'message': 'Restart the simulator from the current checkout.'}
        return {'ready': True, 'code': 'READY', 'message': 'Local simulator and control access are ready.'}
    except httpx.HTTPStatusError as error:
        code = 'SIMULATOR_CONTROL_DENIED' if error.response.status_code in (401, 403) else 'SIMULATOR_VERSION_MISMATCH'
        return {'ready': False, 'code': code,
                'message': 'Restart both local services with the same artifact directory and control configuration.'}
    except (httpx.HTTPError, OSError):
        return {'ready': False, 'code': 'SIMULATOR_UNAVAILABLE',
                'message': 'Start the local simulator before executing a campaign.'}
    except (ValueError, ConfigurationError):
        return {'ready': False, 'code': 'SIMULATOR_CONFIGURATION_INVALID',
                'message': 'Check the local simulator address and control configuration.'}
    finally:
        if client is not None:
            await client.close()


def execution_failure(error):
    """Keep useful failure class/location without persisting raw exception text.

    SDK/HTTP exception messages may include credentials, URLs or response bodies.
    Static explanations and code locations are enough to locate a failure safely.
    """
    from app.providers.runtime import RuntimeProviderError
    from app.contracts.tokens import ModelInputLimit
    from app.lab.agent_history import HistoryChanged
    if isinstance(error, HistoryChanged):
        # Discovery v3 refused before any Explorer request. Its messages are fixed FaultLab text with hash
        # prefixes (never exception text from a provider or SDK), so the plain reason is kept.
        result = {'code': HistoryChanged.code, 'message': str(error), 'provider_dispatch': False}
    elif isinstance(error, ModelInputLimit):
        result = {'code': 'INPUT_LIMIT', 'message': 'Saved evidence exceeds the model input limit. This request was rejected before provider dispatch.',
                  'input_token_bound': error.token_bound, 'input_token_limit': error.token_limit,
                  'provider_dispatch': False}
    elif isinstance(error, RuntimeProviderError):
        result = {'code': error.code, 'message': 'A model request failed; inspect the saved provider diagnostics.',
                  'diagnostics': error.diagnostics}
    elif isinstance(error, httpx.HTTPStatusError):
        result = {'code': 'LOCAL_HTTP_ERROR', 'message': 'A local service rejected the request.',
                  'http_status': error.response.status_code}
    elif isinstance(error, httpx.HTTPError):
        result = {'code': 'LOCAL_CONNECTION_ERROR', 'message': 'A local service could not be reached or timed out.'}
    elif isinstance(error, ConfigurationError):
        result = {'code': 'CONFIGURATION_ERROR', 'message': 'Required configuration is unavailable.',
                  'missing_fields': list(error.missing_fields)}
    else:
        result = {'code': 'EXECUTION_ERROR', 'message': 'Execution failed; inspect the saved error class and code location.'}
    names = {'ValueError', 'TypeError', 'KeyError', 'RuntimeError', 'AttributeError', 'TimeoutError',
             'ConnectionError', 'ConnectError', 'ConnectTimeout', 'ReadTimeout', 'HTTPStatusError',
             'ConfigurationError', 'RuntimeProviderError', 'ModelInputLimit', 'StoreConflict', 'ValidationError', 'AssertionError',
             'HistoryChanged'}
    result['error_class'] = type(error).__name__ if type(error).__name__ in names else 'UnexpectedError'
    root = Path(__file__).resolve().parents[1]
    locations = []
    for frame in traceback.extract_tb(error.__traceback__):
        try:
            relative = Path(frame.filename).resolve().relative_to(root)
        except ValueError:
            continue
        locations.append({'file': relative.as_posix(), 'line': frame.lineno})
    result['locations'] = locations[-8:]
    return result
