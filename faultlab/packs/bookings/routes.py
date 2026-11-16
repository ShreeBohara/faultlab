"""The six business routes of the bookings pack, served over the kernel's dispatch."""

import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from faultlab.core.model import StrictModel
from faultlab.env.kernel.dispatch import dispatch


class PlaceHoldBody(StrictModel):
    booking_id: str
    slot_id: str


class MoveBody(StrictModel):
    booking_id: str
    hold_id: str
    operation_id: str
    idempotency_key: str
    intent_hash: str


class ReleaseBody(StrictModel):
    booking_id: str
    hold_id: str


def router(store, limits):
    api = APIRouter(prefix="/business")

    async def run(request: Request, tool, service, *, payload=None, **identities):
        headers = request.headers
        status, result, delay = dispatch(
            store, limits, world=headers.get("X-FaultLab-World", ""), capability=headers.get("X-FaultLab-Capability", ""),
            call=headers.get("X-FaultLab-Call", ""), attempt=headers.get("X-FaultLab-Attempt", ""), tool=tool, service=service,
            request={**identities, "payload": payload.model_dump(mode="json") if payload is not None else None})
        # The transaction and its locks are released before a genuine socket timeout or disconnect.
        if delay:
            await asyncio.sleep(delay)
        return JSONResponse(status_code=status, content=result)

    @api.get("/bookings/{booking_id}")
    async def get_booking(booking_id: str, request: Request):
        return await run(request, "get_booking", "bookings", booking_id=booking_id)

    @api.get("/bookings/{booking_id}/moves/{operation_id}")
    async def get_move_status(booking_id: str, operation_id: str, request: Request):
        return await run(request, "get_move_status", "bookings", booking_id=booking_id, operation_id=operation_id)

    @api.post("/bookings/{booking_id}/moves")
    async def move_booking(booking_id: str, body: MoveBody, request: Request):
        return await run(request, "move_booking", "bookings", booking_id=booking_id, operation_id=body.operation_id, payload=body)

    @api.get("/holds")
    async def list_holds(request: Request, booking_id: str | None = None):
        return await run(request, "list_holds", "calendar", booking_id=booking_id)

    @api.post("/holds")
    async def place_hold(body: PlaceHoldBody, request: Request):
        return await run(request, "place_hold", "calendar", booking_id=body.booking_id, payload=body)

    @api.post("/holds/{hold_id}/release")
    async def release_hold(hold_id: str, body: ReleaseBody, request: Request):
        return await run(request, "release_hold", "calendar", booking_id=body.booking_id, hold_id=hold_id, payload=body)

    return api
