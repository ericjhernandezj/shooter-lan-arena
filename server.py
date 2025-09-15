import socket
import threading
import pickle
import math
import time
import random

jugadores = {}   # {id: {...}}
id_count = 0
inputs = {}      # {id: {"move": [dx,dy], "shoot": [mx,my]}}
conns = {}  # {id: conn}
health_pickups = []  # Lista de vidas en el mapa: [{"x": x, "y": y, "id": unique_id}, ...]
health_pickup_id = 0  # ID único para cada vida
MAP_WIDTH, MAP_HEIGHT = 2000, 2000
WIDTH, HEIGHT = 800, 600
FPS = 60
lock = threading.Lock()

# Colores disponibles para jugadores
PLAYER_COLORS = [
    (255, 100, 100),  # Rojo
    (100, 255, 100),  # Verde
    (100, 100, 255),  # Azul
    (255, 255, 100),  # Amarillo
    (255, 100, 255),  # Magenta
    (100, 255, 255),  # Cian
    (255, 150, 100),  # Naranja
    (150, 255, 150),  # Verde claro
]

def get_spawn_position():
    """Genera una posición de spawn aleatoria en el mapa"""
    return random.randint(50, MAP_WIDTH-50), random.randint(50, MAP_HEIGHT-50)

def get_player_color():
    """Asigna un color aleatorio al jugador"""
    return random.choice(PLAYER_COLORS)

def spawn_health_pickup():
    """Genera una nueva vida en una posición aleatoria"""
    global health_pickup_id
    health_pickup_id += 1
    return {
        "x": random.randint(30, MAP_WIDTH-30),
        "y": random.randint(30, MAP_HEIGHT-30),
        "id": health_pickup_id
    }

def maintain_health_pickups():
    """Mantiene el número de vidas igual al número de jugadores"""
    global health_pickups
    current_players = len([j for j in jugadores.values() if not j.get("spectator", False)])
    target_pickups = max(1, current_players)  # Mínimo 1 vida

    # Agregar vidas si faltan
    while len(health_pickups) < target_pickups:
        health_pickups.append(spawn_health_pickup())

    # Remover vidas si sobran
    while len(health_pickups) > target_pickups:
        health_pickups.pop()

def manejar_cliente(conn, jugador_id):
    global jugadores, inputs, conns
    try:
        conn.send(pickle.dumps(jugador_id))  # Mandamos ID al cliente
        print(f"[SERVIDOR] Jugador {jugador_id} conectado")
        with lock:
            conns[jugador_id] = conn  # Guardar conexión

        while True:
            try:
                data = conn.recv(4096)
                if not data:
                    break
                input_data = pickle.loads(data)
                with lock:
                    inputs[jugador_id] = input_data
                    # Verificar si el jugador quiere reaparecer
                    if input_data.get("respawn", False) and jugadores[jugador_id].get("spectator", False):
                        # Reaparecer jugador
                        x, y = get_spawn_position()
                        jugadores[jugador_id].update({
                            "x": x, "y": y, "vida": 100, "spectator": False, "balas": []
                        })
                        print(f"[SERVIDOR] Jugador {jugador_id} reapareció en ({x}, {y})")
            except (ConnectionResetError, ConnectionAbortedError):
                break
            except Exception as e:
                print(f"[SERVIDOR] Error procesando datos del jugador {jugador_id}: {e}")
                break
    except Exception as e:
        print(f"[SERVIDOR] Error inicial con jugador {jugador_id}: {e}")

    # Limpiar al desconectar
    with lock:
        if jugador_id in jugadores:
            del jugadores[jugador_id]
        if jugador_id in inputs:
            del inputs[jugador_id]
        if jugador_id in conns:
            del conns[jugador_id]
    print(f"[SERVIDOR] Jugador {jugador_id} desconectado")
    conn.close()

def game_loop():
    global jugadores, inputs, conns, health_pickups
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
            # Mantener número correcto de vidas cada 60 ticks (1 segundo)
            if tick_count % 60 == 0:
                maintain_health_pickups()

            # Procesar inputs y actualizar estado
            for jid, j in jugadores.items():
                if j.get("spectator", False):
                    continue

                inp = inputs.get(jid, {})
                move = inp.get("move", [0,0])

                # Movimiento con velocidad variable
                speed = 7 if inp.get("sprint", False) else 5
                j["x"] += move[0] * speed
                j["y"] += move[1] * speed
                j["x"] = max(0, min(j["x"], MAP_WIDTH-40))
                j["y"] = max(0, min(j["y"], MAP_HEIGHT-40))

                # Verificar colisión con vidas
                player_rect = (j["x"], j["y"], 40, 40)
                for pickup in health_pickups[:]:  # Copia para modificar durante iteración
                    pickup_radius = 15
                    # Distancia entre centro del jugador y centro de la vida
                    dist = math.hypot((j["x"]+20) - pickup["x"], (j["y"]+20) - pickup["y"])
                    if dist < pickup_radius + 20 and j["vida"] < 100:  # Solo si no tiene vida llena
                        # Recoger vida
                        j["vida"] = min(100, j["vida"] + 10)
                        health_pickups.remove(pickup)
                        # Spawn nueva vida inmediatamente
                        health_pickups.append(spawn_health_pickup())
                        print(f"[SERVIDOR] Jugador {jid} recogió vida en ({pickup['x']}, {pickup['y']}) - Vida: {j['vida']}")
                        break

                # Shooting con cooldown
                shoot = inp.get("shoot", None)
                current_time = time.time()

                if shoot == "suicide":
                    j["vida"] -= 10
                elif isinstance(shoot, list) and current_time - j.get("last_shot", 0) > 0.2:  # Cooldown de 200ms
                    mx, my = shoot
                    # Calcular dirección de disparo mejorada
                    cam_x = max(0, min(j["x"] - WIDTH//2, MAP_WIDTH - WIDTH))
                    cam_y = max(0, min(j["y"] - HEIGHT//2, MAP_HEIGHT - HEIGHT))
                    target_x = mx + cam_x
                    target_y = my + cam_y

                    dx, dy = target_x - (j["x"]+20), target_y - (j["y"]+20)
                    dist = math.hypot(dx, dy)
                    if dist > 0:
                        dx, dy = dx/dist, dy/dist
                        j["balas"].append({
                            "x": j["x"]+20, "y": j["y"]+20,
                            "dx": dx, "dy": dy,
                            "owner": jid,
                            "lifetime": 0
                        })
                        j["last_shot"] = current_time

            # Actualizar balas y colisiones
            for jid, j in jugadores.items():
                if j.get("spectator", False):
                    continue

                nuevas_balas = []
                for bala in j["balas"]:
                    bala["x"] += bala["dx"] * 12  # Velocidad aumentada
                    bala["y"] += bala["dy"] * 12
                    bala["lifetime"] += 1

                    # Eliminar balas que salen del mapa o son muy viejas
                    if (0 < bala["x"] < MAP_WIDTH and 0 < bala["y"] < MAP_HEIGHT
                        and bala["lifetime"] < 300):  # 5 segundos a 60fps

                        # Colisión con otros jugadores
                        hit = False
                        for oid, o in jugadores.items():
                            if oid == jid or o.get("spectator", False):
                                continue

                            # Mejorar detección de colisiones
                            if (o["x"] <= bala["x"] <= o["x"]+40 and
                                o["y"] <= bala["y"] <= o["y"]+40):
                                o["vida"] -= 15  # Más daño
                                hit = True
                                # Estadísticas
                                j["kills"] = j.get("kills", 0)
                                if o["vida"] <= 0:
                                    j["kills"] += 1
                                    o["deaths"] = o.get("deaths", 0) + 1
                                break

                        if not hit:
                            nuevas_balas.append(bala)

                j["balas"] = nuevas_balas

            # Modo espectador y regeneración de vida
            for jid, j in jugadores.items():
                if not j.get("spectator", False):
                    if j["vida"] <= 0:
                        j["spectator"] = True
                        j["death_time"] = time.time()
                    elif j["vida"] < 100 and tick_count % 120 == 0:  # Regenerar cada 2 segundos
                        j["vida"] = min(100, j["vida"] + 2)

            # Enviar estado optimizado a cada cliente
            if tick_count % 2 == 0:  # Reducir frecuencia a 30fps
                connections_to_remove = []
                for jid, conn in conns.items():
                    if jid in jugadores:
                        estado = {
                            "jugadores": jugadores.copy(),
                            "jugador_id": jid,
                            "spectator": jugadores[jid].get("spectator", False),
                            "health_pickups": health_pickups.copy(),
                            "tick": tick_count
                        }
                        try:
                            data = pickle.dumps(estado)
                            conn.sendall(data)
                        except (BrokenPipeError, ConnectionResetError):
                            connections_to_remove.append(jid)
                        except Exception as e:
                            print(f"[SERVIDOR] Error enviando a jugador {jid}: {e}")
                            connections_to_remove.append(jid)

                # Limpiar conexiones rotas
                for jid in connections_to_remove:
                    if jid in conns:
                        del conns[jid]

def main():
    global id_count, jugadores
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # Permitir reusar puerto

    try:
        server.bind(("0.0.0.0", 5555))
        server.listen(10)  # Permitir más conexiones concurrentes
        print("[SERVIDOR] Servidor iniciado en puerto 5555...")
        print("[SERVIDOR] Esperando jugadores...")

        # Iniciar game loop
        threading.Thread(target=game_loop, daemon=True).start()

        while True:
            try:
                conn, addr = server.accept()
                print(f"[NUEVA CONEXIÓN] {addr}")
                id_count += 1

                # Crear jugador con posición y color aleatorios
                spawn_x, spawn_y = get_spawn_position()
                color = get_player_color()

                with lock:
                    jugadores[id_count] = {
                        "x": spawn_x, "y": spawn_y,
                        "color": color,
                        "balas": [],
                        "vida": 100,
                        "spectator": False,
                        "kills": 0,
                        "deaths": 0,
                        "last_shot": 0
                    }

                threading.Thread(target=manejar_cliente, args=(conn, id_count)).start()

            except KeyboardInterrupt:
                print("\n[SERVIDOR] Cerrando servidor...")
                break
            except Exception as e:
                print(f"[SERVIDOR] Error aceptando conexión: {e}")

    except Exception as e:
        print(f"[SERVIDOR] Error iniciando servidor: {e}")
    finally:
        server.close()

if __name__ == "__main__":
    main()
