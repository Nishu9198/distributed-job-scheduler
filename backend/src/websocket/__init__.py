"""
WebSocket domain — Live update manager and router.

Provides real-time updates to the frontend dashboard via WebSocket.
Uses a simple pub/sub pattern with Redis for multi-process broadcasting.
"""

import asyncio
import json
from typing import Any

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = structlog.get_logger()

router = APIRouter(tags=["WebSocket"])


class ConnectionManager:
    """
    Manages active WebSocket connections and broadcasts updates.
    
    In a multi-process deployment, Redis pub/sub would be used
    to broadcast across all API instances. For this implementation,
    we use in-process broadcasting (sufficient for single-instance).
    """

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("ws_connected", total=len(self.active_connections))

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        logger.info("ws_disconnected", total=len(self.active_connections))

    async def broadcast(self, event: str, data: Any):
        """Broadcast an event to all connected clients."""
        message = json.dumps({"event": event, "data": data})
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                disconnected.append(connection)

        # Clean up dead connections
        for conn in disconnected:
            try:
                self.active_connections.remove(conn)
            except ValueError:
                pass

    async def send_personal(self, websocket: WebSocket, event: str, data: Any):
        """Send a message to a specific client."""
        message = json.dumps({"event": event, "data": data})
        await websocket.send_text(message)


# Singleton connection manager
manager = ConnectionManager()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for live dashboard updates.
    
    Events broadcast to clients:
    - job:created — New job created
    - job:claimed — Job claimed by worker
    - job:completed — Job completed
    - job:failed — Job failed
    - worker:heartbeat — Worker heartbeat received
    - worker:offline — Worker went offline
    - queue:paused — Queue paused
    - queue:resumed — Queue resumed
    - metrics:update — Dashboard metrics refresh
    """
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive and handle client messages
            data = await websocket.receive_text()
            # Client can send ping/subscribe messages
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await manager.send_personal(
                        websocket, "pong", {"timestamp": msg.get("timestamp")}
                    )
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        manager.disconnect(websocket)


async def broadcast_event(event: str, data: Any):
    """Helper function to broadcast events from service layer."""
    await manager.broadcast(event, data)
