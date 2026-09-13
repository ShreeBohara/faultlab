"""Provider-free simulator process: uvicorn app.simulator.main:app --host 127.0.0.1 --port 8001."""
from fastapi import FastAPI,Request
from fastapi.responses import JSONResponse
from app.config import Settings
from .storage import WorldStore,WorldError
from .control import router as control_router
from .business import router as business_router


def create_app(*,database_dir=None,control_token=None,settings=None):
    settings=settings or Settings.from_env()
    store=WorldStore(database_dir if database_dir is not None else settings.artifact_path/'worlds')
    token=settings.local_control_token() if control_token is None else control_token
    app=FastAPI(title='FaultLab private simulator',docs_url=None,redoc_url=None)
    app.state.store=store
    @app.exception_handler(WorldError)
    async def world_error(request:Request,error:WorldError):return JSONResponse(status_code=error.status,content={'error_code':error.code})
    @app.get('/health')
    def health():return {'status':'ok','service':'faultlab-simulator','schema_version':'faultlab/v1'}
    app.include_router(control_router(store,token));app.include_router(business_router(store))
    return app

app=create_app()
