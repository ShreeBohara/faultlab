"""Saved study results for the dashboard: read-only and offline, with no provider, store or coordinator.

The study pages list the folders under ``Settings.studies_path`` (FAULTLAB_STUDIES_DIR, by default the repository's
``artifacts`` folder) and show each study's declaration, decisions and read-outs through ``faultlab.research.archive``.
Startup does not touch the folder; each request reads published record files only, never a case file, bundle or
trial store.
"""
from pathlib import Path
import sys

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.contracts.models import new_id


def _v2_on_path() -> None:
    """The study reader belongs to the v2 package beside this one, at the repository root."""
    root = Path(__file__).resolve().parents[2]
    if str(root) not in sys.path and (root / 'faultlab' / 'research').is_dir():
        sys.path.append(str(root))


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={'error': {'code': code, 'message': message, 'request_id': new_id('request')}})


def create_studies_router(get_settings) -> APIRouter:
    # The server runs from backend/ (scripts/start-backend.sh), where the repository root is not on the path; the test
    # suite adds it, so a test alone would not notice. Path only: nothing is read here.
    _v2_on_path()
    router = APIRouter(prefix='/api')

    def archive():
        from faultlab.research.archive import StudyArchive
        return StudyArchive(get_settings().studies_path)

    def read(action, missing: str):
        from faultlab.research.archive import StudyNotFound
        try:
            return action()
        except StudyNotFound:
            return _error(404, 'STUDY_NOT_FOUND', missing)
        except (OSError, ValueError, KeyError, TypeError):
            return _error(500, 'STUDY_RECORD_UNREADABLE', 'The saved study record could not be read. Nothing was changed.')

    @router.get('/studies')
    def studies():
        return read(lambda: archive().index(), 'No study folder is available.')

    @router.get('/studies/{study_id}')
    def study(study_id: str):
        return read(lambda: archive().study(study_id), 'No published study has that name.')

    @router.get('/studies/{study_id}/files/{name:path}')
    def study_file(study_id: str, name: str):
        return read(lambda: archive().record_file(study_id, name), 'That study publishes no record file of that name.')

    return router
