"""A provider-free world service: the kernel's control API plus the pack's business routes."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from faultlab.env.kernel.control import router as control_router
from faultlab.env.kernel.errors import WorldError
from faultlab.env.kernel.limits import KernelLimits
from faultlab.env.kernel.storage import WorldStore


def create_app(*, handler, database_dir, control_token: str, limits: KernelLimits | None = None,
               business_router=None) -> FastAPI:
    limits = limits or KernelLimits()
    store = WorldStore(database_dir, handler)
    app = FastAPI(title="FaultLab world kernel", docs_url=None, redoc_url=None)
    app.state.store = store
    app.state.limits = limits

    @app.exception_handler(WorldError)
    async def world_error(request: Request, error: WorldError):
        return JSONResponse(status_code=error.status, content={"error_code": error.code})

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "faultlab-simulator", "schema_version": "faultlab/v1", "pack": handler.pack_id}

    app.include_router(control_router(store, control_token, limits))
    if business_router is not None:
        app.include_router(business_router(store, limits))
    return app
