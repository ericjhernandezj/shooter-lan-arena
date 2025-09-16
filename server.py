import socket
import threading
import pickle
import math
import time
import random

players = {}   # {id: {...}}
id_count = 0
inputs = {}      # {id: {"move": [dx,dy], "shoot": [mx,my]}}
conns = {}  # {id: conn}
health_pickups = []  # List of health pickups on the map : [{"x": x, "y": y, "id": unique_id}, ...]
health_pickup_id = 0  # Unique ID for each health pickup
MAP_WIDTH, MAP_HEIGHT = 2000, 2000
WIDTH, HEIGHT = 800, 600
FPS = 60
lock = threading.Lock()

# Available player colors
PLAYER_COLORS = [
    (255, 100, 100),  # Red
    (100, 255, 100),  # Green
    (100, 100, 255),  # Blue
    (255, 255, 100),  # Yellow
    (255, 100, 255),  # Magenta
    (100, 255, 255),  # Cyan
    (255, 150, 100),  # Orange
    (150, 255, 150),  # Light Green
]

def get_spawn_position():
    """Generate a random spawn position on the map"""
    return random.randint(50, MAP_WIDTH-50), random.randint(50, MAP_HEIGHT-50)

def get_player_color():
    """Assign a random color to the player"""
    return random.choice(PLAYER_COLORS)

def spawn_health_pickup():
    """Generate a new health pickup at a random position"""
    global health_pickup_id
    health_pickup_id += 1
    return {
        "x": random.randint(30, MAP_WIDTH-30),
        "y": random.randint(30, MAP_HEIGHT-30),
        "id": health_pickup_id
    }

def maintain_health_pickups():
    """Maintain the number of health pickups equal to the number of players"""
    global health_pickups
    current_players = len([p for p in players.values() if not p.get("spectator", False)])
    target_pickups = max(1, current_players)  # Min 1 health pickup

    # Add health pickups if needed
    while len(health_pickups) < target_pickups:
        health_pickups.append(spawn_health_pickup())

    # Remove excess health pickups
    while len(health_pickups) > target_pickups:
        health_pickups.pop()

def manage_client(conn, player_id):
    global players, inputs, conns
    try:
        conn.send(pickle.dumps(player_id))  # Send player ID to client
        print(f"[SERVER] Player {player_id} connected.")
        with lock:
            conns[player_id] = conn  # Save connection

        while True:
            try:
                data = conn.recv(4096)
                if not data:
                    break
                input_data = pickle.loads(data)
                with lock:
                    inputs[player_id] = input_data
                    # Verify if player wants to respawn
                    if input_data.get("respawn", False) and players[player_id].get("spectator", False):
                        # Respawn player
                        x, y = get_spawn_position()
                        players[player_id].update({
                            "x": x, "y": y, "health": 100, "spectator": False, "bullets": []
                        })
                        print(f"[SERVER] Player {player_id} respawned at ({x}, {y})")
            except (ConnectionResetError, ConnectionAbortedError):
                break
            except Exception as e:
                print(f"[SERVER] Error processing {player_id} player data: {e}")
                break
    except Exception as e:
        print(f"[SERVER] Initial error with player {player_id}: {e}")

    # Clean up on disconnect
    with lock:
        if player_id in players:
            del players[player_id]
        if player_id in inputs:
            del inputs[player_id]
        if player_id in conns:
            del conns[player_id]
    print(f"[SERVER] Player {player_id} disconnected.")
    conn.close()

def game_loop():
    global players, inputs, conns, health_pickups
    last_time = time.time()
    tick_count = 0

    while True:
        now = time.time()
        dt = now - last_time
        if dt < 1/FPS:
            time.sleep(1/FPS - dt)

        last_time = now
        tick_count += 1

        with lock:
            # Maintain correct number of health pickups every 60 ticks (1 second)
            if tick_count % 60 == 0:
                maintain_health_pickups()

            # Process player movements and actions
            for pid, p in players.items():
                if p.get("spectator", False):
                    continue

                inp = inputs.get(pid, {})
                move = inp.get("move", [0,0])

                # Movement with variable speed
                speed = 7 if inp.get("sprint", False) else 5
                p["x"] += move[0] * speed
                p["y"] += move[1] * speed
                p["x"] = max(0, min(p["x"], MAP_WIDTH-40))
                p["y"] = max(0, min(p["y"], MAP_HEIGHT-40))

                # Verify heatlh pickup collisions
                player_rect = (p["x"], p["y"], 40, 40)
                for pickup in health_pickups[:]:  # Copy to avoid modification during iteration
                    pickup_radius = 15
                    # Distance between player center and health center
                    dist = math.hypot((p["x"]+20) - pickup["x"], (p["y"]+20) - pickup["y"])
                    if dist < pickup_radius + 20 and p["health"] < 100:  # Only if not full health
                        # Pickup collected
                        p["health"] = min(100, p["health"] + 10)
                        health_pickups.remove(pickup)
                        # Spawn a new health pickup
                        health_pickups.append(spawn_health_pickup())
                        print(f"[SERVER] Player {pid} picked health up at ({pickup['x']}, {pickup['y']}) - Health: {p['health']}")
                        break

                # Shooting mechanics
                shoot = inp.get("shoot", None)
                current_time = time.time()

                if shoot == "suicide":
                    p["health"] -= 10
                elif isinstance(shoot, list) and current_time - p.get("last_shot", 0) > 0.2:  # 200ms cooldown
                    mx, my = shoot
                    # Calculate camera offset
                    cam_x = max(0, min(p["x"] - WIDTH//2, MAP_WIDTH - WIDTH))
                    cam_y = max(0, min(p["y"] - HEIGHT//2, MAP_HEIGHT - HEIGHT))
                    target_x = mx + cam_x
                    target_y = my + cam_y

                    dx, dy = target_x - (p["x"]+20), target_y - (p["y"]+20)
                    dist = math.hypot(dx, dy)
                    if dist > 0:
                        dx, dy = dx/dist, dy/dist
                        p["bullets"].append({
                            "x": p["x"]+20, "y": p["y"]+20,
                            "dx": dx, "dy": dy,
                            "owner": pid,
                            "lifetime": 0
                        })
                        p["last_shot"] = current_time

            # Update bullets positions and check for collisions
            for pid, p in players.items():
                if p.get("spectator", False):
                    continue

                new_bullets = []
                for bullet in p["bullets"]:
                    bullet["x"] += bullet["dx"] * 12  # Velocity increased
                    bullet["y"] += bullet["dy"] * 12
                    bullet["lifetime"] += 1

                    # Delete bullets that go out of bounds or are too old
                    if (0 < bullet["x"] < MAP_WIDTH and 0 < bullet["y"] < MAP_HEIGHT
                        and bullet["lifetime"] < 300):  # 5 seconds at 60fps

                        # Collision detection with other players
                        hit = False
                        for oid, o in players.items():
                            if oid == pid or o.get("spectator", False):
                                continue

                            # Improved collision detection
                            if (o["x"] <= bullet["x"] <= o["x"]+40 and
                                o["y"] <= bullet["y"] <= o["y"]+40):
                                o["health"] -= 15  # More damage
                                hit = True
                                # Statistics
                                p["kills"] = p.get("kills", 0)
                                if o["health"] <= 0:
                                    p["kills"] = p.get("kills", 0) + 1
                                    o["deaths"] = o.get("deaths", 0) + 1
                                break

                        if not hit:
                            new_bullets.append(bullet)

                p["bullets"] = new_bullets

            # Spectator mode and health regeneration
            for pid, p in players.items():
                if not p.get("spectator", False):
                    if p["health"] <= 0:
                        p["spectator"] = True
                        p["death_time"] = time.time()
                    elif p["health"] < 100 and tick_count % 120 == 0:  # Regenerate every 2 seconds
                        p["health"] = min(100, p["health"] + 2)

            # Send game state to all players
            if tick_count % 2 == 0:  # Reduce frequency to every 2 ticks (30 times per second)
                connections_to_remove = []
                for pid, conn in conns.items():
                    if pid in players:
                        state = {
                            "players": players.copy(),
                            "player_id": pid,
                            "spectator": players[pid].get("spectator", False),
                            "health_pickups": health_pickups.copy(),
                            "tick": tick_count
                        }
                        try:
                            data = pickle.dumps(state)
                            conn.sendall(data)
                        except (BrokenPipeError, ConnectionResetError):
                            connections_to_remove.append(pid)
                        except Exception as e:
                            print(f"[SERVER] Error sendint to player {pid}: {e}")
                            connections_to_remove.append(pid)

                # Clean up disconnected players
                for pid in connections_to_remove:
                    if pid in conns:
                        del conns[pid]

def main():
    global id_count, players
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # Allow address reuse

    try:
        server.bind(("0.0.0.0", 5555))
        server.listen(10)  # Allow up to 10 connections in the queue
        print("[SERVER] Server starting in port 5555...")
        print("[SERVER] Waiting for players...")

        # Start game loop in a separate thread
        threading.Thread(target=game_loop, daemon=True).start()

        while True:
            try:
                conn, addr = server.accept()
                print(f"[NEW CONNECTION] {addr}")
                id_count += 1

                # Create new player
                spawn_x, spawn_y = get_spawn_position()
                color = get_player_color()

                with lock:
                    players[id_count] = {
                        "x": spawn_x, "y": spawn_y,
                        "color": color,
                        "bullets": [],
                        "health": 100,
                        "spectator": False,
                        "kills": 0,
                        "deaths": 0,
                        "last_shot": 0
                    }

                threading.Thread(target=manage_client, args=(conn, id_count)).start()

            except KeyboardInterrupt:
                print("\n[SERVER] Closing server...")
                break
            except Exception as e:
                print(f"[SERVER] Error accepting connections: {e}")

    except Exception as e:
        print(f"[SERVER] Error starting server: {e}")
    finally:
        server.close()

if __name__ == "__main__":
    main()
