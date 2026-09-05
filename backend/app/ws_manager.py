"""WebSocket connection manager for /ws/alerts — real-time push when a
tagged plate reappears. Department-scoped the same way reads elsewhere in
Model 2 are: a connection with department=None (super_admin/viewer) sees
every alert; a department_admin connection only sees alerts for their own
department's cameras."""

import asyncio
import logging
from typing import Optional

from fastapi import WebSocket

logger = logging.getLogger("ws_manager")


class ConnectionManager:
    def __init__(self):
        self._connections: dict[WebSocket, Optional[str]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket, department: Optional[str]):
        await ws.accept()
        async with self._lock:
            self._connections[ws] = department

    async def disconnect(self, ws: WebSocket):
        async with self._lock:
            self._connections.pop(ws, None)

    async def broadcast(self, payload: dict, camera_department: Optional[str]):
        async with self._lock:
            targets = list(self._connections.items())
        for ws, scope in targets:
            if scope is not None and scope != camera_department:
                continue
            try:
                await ws.send_json(payload)
            except Exception as e:
                logger.warning("Dropping dead alert websocket: %s", e)
                await self.disconnect(ws)


manager = ConnectionManager()
