"""gr2_ws — WebSocket travel command."""
import json
import asyncio
import time
import websockets
from gr2_config import WS_BASE

# === WS COMMAND ===
async def ws_travel(token, char_id, target_zone, timeout=45):
    """Travel to target zone via WebSocket. Returns True/False/error string."""
    try:
        import websockets
    except ImportError:
        return "no websockets library"

    # Use destination-only approach: server knows current location
    ws_url = f"{WS_BASE}/ws?token={token}&characterId={char_id}"
    try:
        async with asyncio.timeout(timeout):
            async with websockets.connect(ws_url, ping_interval=10, ping_timeout=5) as ws:
                # Drain init messages
                for _ in range(10):
                    try:
                        await asyncio.wait_for(ws.recv(), timeout=0.5)
                    except (asyncio.TimeoutError, asyncio.CancelledError):
                        break

                # Stop combat first (blocks travel)
                await ws.send(json.dumps({
                    "type": "combat:stop_attack",
                    "payload": {},
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
                }))
                await asyncio.sleep(0.5)

                # Send travel
                await ws.send(json.dumps({
                    "type": "start_travel",
                    "payload": {"path": [target_zone]},
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
                }))

                # Wait for arrival
                while True:
                    msg = await asyncio.wait_for(ws.recv(), timeout=60)
                    data = json.loads(msg)
                    if data.get('type') == 'travel_complete':
                        return True
                    elif data.get('type') == 'error':
                        return f"travel error: {data.get('payload', {}).get('message', 'unknown')}"

    except asyncio.TimeoutError:
        return "timed out"
    except Exception as e:
        return str(e)


# === MAIN ===

