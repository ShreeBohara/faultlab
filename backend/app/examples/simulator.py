"""Compose the existing simulator routes without importing its server entry point.

The server entry point intentionally reads deployment settings at import time.
This local example requires explicit paths and a local capability instead. Only
ASGI wiring lives here; the world, business tools and authorization are shared.
The original service bytes and earlier bundle identities remain unchanged.
"""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.simulator.storage import WorldStore, WorldError
from app.simulator.control import router as control_router
from app.simulator.business import router as business_router


def create_app(*, database_dir, control_token, settings):
    if not control_token:
        raise ValueError('An explicit local control capability is required')
    store = WorldStore(database_dir)
    app = FastAPI(title='FaultLab private simulator', docs_url=None, redoc_url=None)
    app.state.store = store

    @app.exception_handler(WorldError)
    async def world_error(request: Request, error: WorldError):
        return JSONResponse(status_code=error.status, content={'error_code': error.code})

    @app.get('/health')
    def health():
        return {'status': 'ok', 'service': 'faultlab-simulator', 'schema_version': 'faultlab/v1'}

    app.include_router(control_router(store, control_token))
    app.include_router(business_router(store))
    return app
