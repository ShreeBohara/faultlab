"""Default tests prohibit network; explicit HTTP tests allow loopback only."""
import ipaddress
import socket
import pytest


def _local(host):
    if isinstance(host, bytes): host=host.decode()
    if host == 'localhost': return True
    try: return ipaddress.ip_address(host).is_loopback
    except (ValueError, TypeError): return False


@pytest.fixture(autouse=True)
def prohibit_network(monkeypatch, request):
    permit = request.node.get_closest_marker('localhost_http') is not None
    original_gai=socket.getaddrinfo
    original_connect=socket.socket.connect
    original_connect_ex=socket.socket.connect_ex
    original_create=socket.create_connection
    def verify(address):
        if not permit or not isinstance(address,tuple) or not _local(address[0]):
            raise AssertionError('Offline tests may only use explicitly marked loopback HTTP')
    def gai(host,*args,**kwargs):
        verify((host,0));return original_gai(host,*args,**kwargs)
    def connect(sock,address):
        if sock.family == socket.AF_UNIX: return original_connect(sock,address)
        verify(address);return original_connect(sock,address)
    def connect_ex(sock,address):
        verify(address);return original_connect_ex(sock,address)
    def create(address,*args,**kwargs):
        verify(address);return original_create(address,*args,**kwargs)
    monkeypatch.setattr(socket,'getaddrinfo',gai)
    monkeypatch.setattr(socket,'create_connection',create)
    monkeypatch.setattr(socket.socket,'connect',connect)
    monkeypatch.setattr(socket.socket,'connect_ex',connect_ex)
