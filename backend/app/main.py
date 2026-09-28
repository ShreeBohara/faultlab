"""Local application entrypoint. Health/startup never contact a provider."""
from contextlib import asynccontextmanager
import json
import os
from threading import RLock
from urllib.parse import urlsplit
from uuid import uuid4
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

# The dashboard and API are local-only. Any other Host is refused, which blocks
# DNS-rebinding pages from reading the store identity or posting uploads/runs.
LOCAL_HOSTS = frozenset({'localhost', '127.0.0.1', '::1'})
UNSAFE_METHODS = frozenset({'POST', 'PUT', 'PATCH', 'DELETE'})


def _hostname(value):
    """Host header or Origin authority -> lowercase hostname without port/brackets."""
    try:
        parsed = urlsplit(value if '//' in value else '//' + value)
        return (parsed.hostname or '').lower()
    except ValueError:
        return ''


def configured_hosts(extra=None):
    names = set(LOCAL_HOSTS)
    raw = os.environ.get('FAULTLAB_ALLOWED_HOSTS', '') if extra is None else ','.join(extra)
    names.update(name.strip().lower() for name in raw.split(',') if name.strip())
    return frozenset(names)


class LocalHostGuard:
    """Refuse foreign Host headers, and browser writes from a foreign Origin."""

    def __init__(self, app, allowed):
        self.app, self.allowed = app, allowed

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        headers = {key.decode('latin-1').lower(): value.decode('latin-1') for key, value in scope['headers']}
        reason = None
        if _hostname(headers.get('host', '')) not in self.allowed:
            reason = 'Requests must address this local FaultLab service by a local host name.'
        elif scope['method'] in UNSAFE_METHODS and 'origin' in headers and _hostname(headers['origin']) not in self.allowed:
            reason = 'Changes are accepted only from the local FaultLab dashboard.'
        if reason is None:
            return await self.app(scope, receive, send)
        body = json.dumps({'error': {'code': 'HOST_NOT_ALLOWED', 'message': reason, 'request_id': str(uuid4())}}).encode()
        await send({'type': 'http.response.start', 'status': 403,
                    'headers': [(b'content-type', b'application/json'), (b'content-length', str(len(body)).encode())]})
        await send({'type': 'http.response.body', 'body': body})


def create_app(*, settings=None, coordinator=None, allowed_hosts=None):
    lock=RLock()
    current=coordinator
    selected=settings or getattr(coordinator, 'settings', None)

    def get_settings():
        nonlocal selected
        with lock:
            if current is not None and hasattr(current, 'settings'):
                return current.settings
            if selected is None:
                from app.config import Settings
                selected=Settings.from_env()
            return selected

    def get_coordinator():
        nonlocal current
        with lock:
            if current is None:
                configured = get_settings()
                if configured.faultlab_read_only:
                    from app.lab.dashboard import ArchiveCoordinator
                    current = ArchiveCoordinator(configured)
                else:
                    from app.lab.coordinator import LabCoordinator
                    current=LabCoordinator(configured)
            return current

    @asynccontextmanager
    async def lifespan(app):
        yield
        if current is not None:
            await current.close()

    app=FastAPI(title='FaultLab',version='0.2.0',lifespan=lifespan)
    app.state.get_coordinator=get_coordinator

    @app.get('/api/health')
    def health() -> dict[str,str]:
        return {'status':'ok','service':'faultlab-backend'}

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request:Request,error:RequestValidationError):
        # Pydantic errors can contain supplied input. Return only the safe contract error.
        return JSONResponse(status_code=422,content={'error':{'code':'INVALID_REQUEST','message':'Request does not match the FaultLab contract.','request_id':str(uuid4())}})

    from app.lab.api import create_router
    app.include_router(create_router(get_coordinator, get_settings=get_settings))
    app.add_middleware(LocalHostGuard, allowed=configured_hosts(allowed_hosts))
    return app

app=create_app()
