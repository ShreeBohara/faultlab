"""Product review ($0, offline): serve the built dashboard (frontend/dist) and this build's API over the review's scratch
store copy, on 127.0.0.1 only, for looking at the pages in a local browser.

Run from faultlab/backend (background):  ../.venv/bin/python -B .../review_dashboard_server.py PORT
The store is the scratch copy review_scripted_campaigns.py left at /Users/shree/FaultLab_Scratch/review-product-fireability/lab
(outside the synced Desktop). Nothing in the repo is written. Settings are built explicitly (no .env is read; review_guard
refuses it), and every non-loopback socket is refused.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import review_guard  # noqa: E402

BACKEND = Path.cwd()
sys.path.insert(0, str(BACKEND))
DIST = BACKEND.parent / 'frontend' / 'dist'
SCRATCH = Path('/Users/shree/FaultLab_Scratch/review-product-fireability/lab')


def main(port):
    import uvicorn
    from fastapi.staticfiles import StaticFiles
    from app.config import Settings
    from app.lab.coordinator import LabCoordinator
    from app.main import create_app
    owner = LabCoordinator(Settings(faultlab_artifact_dir=str(SCRATCH), wandb_model='deepseek-ai/DeepSeek-V3.1',
                                    wandb_explorer_model='deepseek-ai/DeepSeek-V4-Pro-0813'))
    app = create_app(coordinator=owner)
    app.mount('/', StaticFiles(directory=str(DIST), html=True), name='dashboard')
    uvicorn.run(app, host='127.0.0.1', port=port, log_level='warning')


if __name__ == '__main__':
    main(int(sys.argv[1]))
