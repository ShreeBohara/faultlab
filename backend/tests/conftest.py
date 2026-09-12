"""All backend tests run offline, including accidental provider requests."""

import socket

import pytest


@pytest.fixture(autouse=True)
def prohibit_network(monkeypatch):
    def fail_network(*args, **kwargs):
        raise AssertionError("Offline tests must not make network requests")

    monkeypatch.setattr(socket, "getaddrinfo", fail_network)
    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(socket.socket, "connect", fail_network)
    monkeypatch.setattr(socket.socket, "connect_ex", fail_network)
