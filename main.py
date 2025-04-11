from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import uvicorn
from typing import List, Dict, Set, Tuple, Literal, Optional
import logging
import time
from urllib.parse import unquote

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Mount static files directory
app.mount("/static", StaticFiles(directory="static"), name="static")

# Setup Jinja2 templates
templates = Jinja2Templates(directory="templates")

# State Management
class ConnectionManager:
    def __init__(self):
        # Store websocket: (client_id, role)
        self.active_connections: Dict[WebSocket, Tuple[str, Literal["player", "admin"]]] = {}
        self.buzz_order: List[Tuple[str, float]] = [] # Store (client_id, timestamp)
        self.buzzed_clients: Set[WebSocket] = set() # Players who buzzed this round
        # No longer need next_player_id
        self.admin_count = 0

    def get_client_info(self, websocket: WebSocket) -> Tuple[str, Literal["player", "admin"]]:
        return self.active_connections.get(websocket, ("Unknown Client", "player"))

    async def connect(self, websocket: WebSocket, role: Literal["player", "admin"], name: Optional[str] = None):
        await websocket.accept()
        client_id = "Admin" # Default/fallback

        if role == "player":
            # Use provided name, fallback if empty or missing
            safe_name = name if name and name.strip() else f"لاعب مجهول" # Unknown Player
            client_id = safe_name
            # Optional: Check for duplicate names and append a number? For now, allow duplicates.
        else: # Admin role
            self.admin_count += 1
            client_id = f"Admin {self.admin_count}"

        self.active_connections[websocket] = (client_id, role)
        logger.info(f"{client_id} ({role}) connected. Total clients: {len(self.active_connections)}")
        # Send current state to the newly connected client
        await self.send_state(websocket)

    def disconnect(self, websocket: WebSocket):
        client_id, role = self.active_connections.pop(websocket, ("Unknown Client", "player"))
        self.buzzed_clients.discard(websocket) # Remove if they were in the set
        if role == "admin":
            # Check if admin_count > 0 before decrementing, though pop should handle missing keys
             if self.admin_count > 0: self.admin_count -=1
        logger.info(f"{client_id} ({role}) disconnected. Total clients: {len(self.active_connections)}")

    def _get_state_message(self, websocket: WebSocket) -> dict:
        """Helper to create the state message based on client role."""
        client_id, role = self.get_client_info(websocket)
        ordered_buzzers = [cid for cid, ts in self.buzz_order]
        rank = None
        can_buzz = False

        if role == "player":
            try:
                # Find rank (1-based index) for players
                rank = ordered_buzzers.index(client_id) + 1
            except ValueError:
                rank = None # This player hasn't buzzed yet
            # Player can buzz if they haven't buzzed this round
            can_buzz = websocket not in self.buzzed_clients

        return {
            "buzz_order": ordered_buzzers,
            "your_rank": rank, # Will be None for admin or unbuzzed players
            "can_buzz": can_buzz, # Will be False for admin or buzzed players
            "round_active": len(self.buzz_order) > 0 # Is the reset button needed? (Used by admin)
        }

    async def send_state(self, websocket: WebSocket):
        """Sends the current buzzer state to a specific client."""
        message = self._get_state_message(websocket)
        client_id, role = self.get_client_info(websocket)
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Error sending state to {client_id} ({role}): {e}")


    async def broadcast_state(self):
        """Broadcasts the current buzzer state to all connected clients."""
        logger.info(f"Broadcasting state. Buzz order: {[cid for cid, ts in self.buzz_order]}")
        disconnected_sockets = []
        # Use items() to safely iterate while potentially modifying the dict
        for connection, (client_id, role) in list(self.active_connections.items()):
            message = self._get_state_message(connection)
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.warning(f"Failed to send to {client_id} ({role}): {e}. Marking for removal.")
                disconnected_sockets.append(connection)

        # Clean up disconnected sockets after broadcast
        for sock in disconnected_sockets:
            # Check if socket still exists before disconnecting
            if sock in self.active_connections:
                self.disconnect(sock)


    def record_buzz(self, websocket: WebSocket) -> bool:
        """Records a buzz if the client is a player and hasn't already buzzed."""
        client_id, role = self.get_client_info(websocket)
        if role == "admin":
            logger.warning(f"Admin ({client_id}) attempted to buzz. Ignored.")
            return False

        if websocket not in self.buzzed_clients:
            timestamp = time.time()
            self.buzz_order.append((client_id, timestamp))
            self.buzzed_clients.add(websocket)
            logger.info(f"Buzz recorded for {client_id}. Rank: {len(self.buzz_order)}")
            return True
        else:
            logger.info(f"{client_id} tried to buzz again.")
            return False

    def reset_buzzer(self, websocket: WebSocket) -> bool:
        """Resets the buzzer order if the requesting client is an admin."""
        client_id, role = self.get_client_info(websocket)
        if role != "admin":
            logger.warning(f"Player ({client_id}) attempted to reset. Denied.")
            return False

        if self.buzz_order or self.buzzed_clients: # Only reset if needed
            self.buzz_order = []
            self.buzzed_clients = set()
            logger.info(f"Buzzer reset by Admin ({client_id})")
            return True
        logger.info(f"Admin ({client_id}) attempted reset, but already reset.")
        return False

manager = ConnectionManager()

# Name entry endpoint
@app.get("/enter_name", response_class=HTMLResponse)
async def get_name_entry(request: Request):
    return templates.TemplateResponse("name_entry.html", {"request": request})

# Player endpoint (main page)
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    # This page now expects the name to be in localStorage, handled by JS redirect
    return templates.TemplateResponse("index.html", {"request": request})

# Admin endpoint
@app.get("/admin", response_class=HTMLResponse)
async def read_admin(request: Request):
    return templates.TemplateResponse("admin.html", {"request": request})


@app.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    role: Literal["player", "admin"] = Query("player"),
    name: Optional[str] = Query(None) # Add name query parameter
    ):
    # Decode the name if provided (it's URL encoded by the JS)
    player_name = unquote(name) if name else None
    await manager.connect(websocket, role, player_name)
    client_id, _ = manager.get_client_info(websocket) # Get assigned ID/name

    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action")
            logger.info(f"Received action '{action}' from {client_id} ({role})")

            if action == "buzz":
                if manager.record_buzz(websocket):
                    await manager.broadcast_state()
            elif action == "reset":
                if manager.reset_buzzer(websocket):
                    await manager.broadcast_state()
            else:
                 logger.warning(f"Unknown action '{action}' received from {client_id} ({role})")

    except WebSocketDisconnect:
        if websocket in manager.active_connections:
            manager.disconnect(websocket)
        logger.info(f"WebSocket disconnected for {client_id} ({role})")
    except Exception as e:
        logger.error(f"Error in WebSocket handler for {client_id} ({role}): {e}")
        if websocket in manager.active_connections:
             manager.disconnect(websocket)


if __name__ == "__main__":
    print("Starting server on http://0.0.0.0:8000")
    print("Player Entry URL: http://<your-local-ip>:8000/enter_name")
    print("Admin URL:        http://<your-local-ip>:8000/admin")
    print("Ensure firewall allows port 8000. Use ngrok if needed.")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)