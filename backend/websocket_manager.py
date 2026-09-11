from typing import Dict, List
from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[int, WebSocket] = {}

    async def connect(self, websocket: WebSocket, user_id: int):
        await websocket.accept()
        if user_id in self.active_connections:
            try:
                await self.active_connections[user_id].close()
            except Exception:
                pass
        self.active_connections[user_id] = websocket
        print(f"✅ User {user_id} connected. Total: {len(self.active_connections)}")

    def disconnect(self, user_id: int):
        if user_id in self.active_connections:
            del self.active_connections[user_id]
            print(f"❌ User {user_id} disconnected. Total: {len(self.active_connections)}")

    def is_online(self, user_id: int) -> bool:
        return user_id in self.active_connections

    def get_online_users(self) -> List[int]:
        return list(self.active_connections.keys())

    async def send_personal_message(self, message: str, user_id: int) -> bool:
        if user_id not in self.active_connections:
            return False
        try:
            await self.active_connections[user_id].send_text(message)
            return True
        except Exception as e:
            print(f"❌ Error sending to {user_id}: {e}")
            self.disconnect(user_id)
            return False

    async def broadcast(self, message: str, exclude_user_id: int = None):
        disconnected = []
        for user_id, connection in list(self.active_connections.items()):
            if exclude_user_id and user_id == exclude_user_id:
                continue
            try:
                await connection.send_text(message)
            except Exception as e:
                print(f"❌ Error broadcasting to {user_id}: {e}")
                disconnected.append(user_id)
        for user_id in disconnected:
            self.disconnect(user_id)

    async def broadcast_to_users(self, message: str, user_ids: List[int]):
        for user_id in user_ids:
            await self.send_personal_message(message, user_id)


manager = ConnectionManager()