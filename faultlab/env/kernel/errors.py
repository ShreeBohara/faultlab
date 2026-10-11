class WorldError(Exception):
    """A refused request: a fixed error code, the HTTP status to return, and an optional reply delay.

    The delay lets a fixture cut a reply off after the transaction closes (a genuine socket
    timeout) while the response is still a refusal.
    """

    def __init__(self, code: str, status: int = 409, *, delay: float = 0.0):
        super().__init__(code)
        self.code, self.status, self.delay = code, status, delay
