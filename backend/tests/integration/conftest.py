"""Real loopback service fixture for cross-domain acceptance."""
import socket
import threading
import time
import pytest
import uvicorn
from app.config import Settings


@pytest.fixture
def simulator_server(tmp_path):
    from app.simulator.main import create_app
    listener=socket.socket();listener.bind(('127.0.0.1',0))
    port=listener.getsockname()[1]
    app=create_app(database_dir=tmp_path/'worlds',control_token='integration-control',settings=Settings())
    server=uvicorn.Server(uvicorn.Config(app,log_level='error',lifespan='off'))
    thread=threading.Thread(target=server.run,kwargs={'sockets':[listener]},daemon=True)
    thread.start()
    deadline=time.monotonic()+5
    while not server.started and time.monotonic()<deadline:time.sleep(.01)
    assert server.started
    try:yield f'http://127.0.0.1:{port}',app
    finally:
        server.should_exit=True;thread.join(timeout=8);listener.close()
        assert not thread.is_alive()
