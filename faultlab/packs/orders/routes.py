"""The four business routes of the orders pack, served over the kernel's dispatch."""

import asyncio
from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from faultlab.env.kernel.dispatch import dispatch
from faultlab.packs.orders.models import NotificationRequest, UpgradeRequest


def router(store, limits):
    api = APIRouter(prefix="/business")

    async def run(request: Request, tool, service, *, order_id=None, operation_id=None, payload=None):
        headers = request.headers
        status, result, delay = dispatch(
            store, limits, world=headers.get("X-FaultLab-World", ""), capability=headers.get("X-FaultLab-Capability", ""),
            call=headers.get("X-FaultLab-Call", ""), attempt=headers.get("X-FaultLab-Attempt", ""), tool=tool, service=service,
            request={"order_id": order_id, "operation_id": operation_id,
                     "payload": payload.model_dump(mode="json") if payload is not None else None})
        # The transaction and its locks are released before a genuine socket timeout or disconnect.
        if delay:
            await asyncio.sleep(delay)
        return JSONResponse(status_code=status, content=result)

    @api.get("/orders/{order_id}")
    async def get_order(order_id: str, request: Request):
        return await run(request, "get_order", "orders", order_id=order_id)

    @api.post("/orders/{order_id}/upgrade")
    async def upgrade(order_id: str, body: UpgradeRequest, request: Request):
        return await run(request, "update_order", "orders", order_id=order_id, operation_id=body.operation_id, payload=body)

    @api.get("/operations/{service}/{operation_id}")
    async def status(service: Literal["orders", "notifications"], operation_id: str, request: Request):
        return await run(request, "get_operation_status", service, operation_id=operation_id)

    @api.post("/notifications")
    async def notify(body: NotificationRequest, request: Request):
        return await run(request, "send_confirmation", "notifications", order_id=body.order_id, operation_id=body.operation_id, payload=body)

    return api
