"""Local application entrypoint. Health/startup never contact a provider."""
from contextlib import asynccontextmanager
from threading import RLock
from uuid import uuid4
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def create_app(*, settings=None, coordinator=None):
    lock=RLock()
    current=coordinator

    def get_coordinator():
        nonlocal current
        with lock:
            if current is None:
                from app.config import Settings
                from app.lab.coordinator import LabCoordinator
                current=LabCoordinator(settings or Settings.from_env())
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
    app.include_router(create_router(get_coordinator))
    return app

app=create_app()
