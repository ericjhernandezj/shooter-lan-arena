import pygame
import socket
import pickle
import math
import time

# Configuración cliente
WIDTH, HEIGHT = 800, 600          # Ventana
MAP_WIDTH, MAP_HEIGHT = 2000, 2000  # Mapa
FPS = 60

def conectar():
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.settimeout(10)  # Timeout para conexión
    try:
        # client.connect(("127.0.0.1", 5555))
        client.connect(("127.0.0.1", 5555))
        client.settimeout(None)  # Remover timeout después de conectar
        return client
    except socket.timeout:
        print("[CLIENTE] Timeout conectando al servidor")
        return None
    except Exception as e:
        print(f"[CLIENTE] Error conectando: {e}")
        return None

def main():
    pygame.init()
    win = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Shooter LAN - Arena")
    clock = pygame.time.Clock()

    # Fuentes para UI
    font_small = pygame.font.SysFont(None, 24)
    font_medium = pygame.font.SysFont(None, 32)
    font_large = pygame.font.SysFont(None, 48)

    client = conectar()
    if not client:
        print("[CLIENTE] No se pudo conectar al servidor")
        return

    # Recibir ID del servidor
    try:
        client.settimeout(5)
        jugador_id = pickle.loads(client.recv(1024))
        client.settimeout(None)
        print(f"[CLIENTE] Conectado con ID {jugador_id}")
    except Exception as e:
        print(f"[CLIENTE] Error al recibir ID del servidor: {e}")
        return

    # Estado inicial
    spectator = False
    cam_x, cam_y = 0, 0
    jugadores = {}
    health_pickups = []  # Inicializar lista de pickups de salud
    last_network_time = time.time()
    connection_lost = False

    # Estadísticas de rendimiento
    fps_counter = 0
    fps_time = time.time()
    current_fps = 0

    run = True
    while run:
        clock.tick(FPS)
        fps_counter += 1

        # Calcular FPS cada segundo
        if time.time() - fps_time >= 1.0:
            current_fps = fps_counter
            fps_counter = 0
            fps_time = time.time()

        move = [0, 0]
        shoot = None
        sprint = False
        respawn = False

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                run = False
            if not spectator:
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    mx, my = pygame.mouse.get_pos()
                    shoot = [mx, my]
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_DELETE:
                        shoot = "suicide"
            else:
                # En modo espectador, permitir respawn con R
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_r:
                        respawn = True

        keys = pygame.key.get_pressed()
        if not spectator:
            if keys[pygame.K_a] or keys[pygame.K_LEFT]: move[0] -= 1
            if keys[pygame.K_d] or keys[pygame.K_RIGHT]: move[0] += 1
            if keys[pygame.K_w] or keys[pygame.K_UP]: move[1] -= 1
            if keys[pygame.K_s] or keys[pygame.K_DOWN]: move[1] += 1
            if keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]: sprint = True
        else:
            # Movimiento de cámara en modo espectador
            speed = 15 if keys[pygame.K_LSHIFT] else 10
            if keys[pygame.K_a] or keys[pygame.K_LEFT]: cam_x -= speed
            if keys[pygame.K_d] or keys[pygame.K_RIGHT]: cam_x += speed
            if keys[pygame.K_w] or keys[pygame.K_UP]: cam_y -= speed
            if keys[pygame.K_s] or keys[pygame.K_DOWN]: cam_y += speed
            cam_x = max(0, min(cam_x, MAP_WIDTH - WIDTH))
            cam_y = max(0, min(cam_y, MAP_HEIGHT - HEIGHT))

        # Enviar inputs al servidor con manejo de errores
        try:
            input_data = {"move": move, "shoot": shoot, "sprint": sprint, "respawn": respawn}
            client.sendall(pickle.dumps(input_data))
            connection_lost = False
        except Exception as e:
            if not connection_lost:
                print(f"[CLIENTE] Error enviando datos: {e}")
                connection_lost = True

        # Recibir estado del servidor con timeout
        try:
            client.settimeout(0.1)  # Timeout corto para no bloquear
            data = client.recv(16384)
            client.settimeout(None)

            if not data:
                print("[CLIENTE] Servidor cerró conexión")
                break

            estado = pickle.loads(data)
            jugadores = estado["jugadores"]
            spectator = estado.get("spectator", False)
            health_pickups = estado.get("health_pickups", [])  # Recibir vidas
            last_network_time = time.time()

            # Actualizar cámara si no es espectador
            if not spectator and jugador_id in jugadores:
                x = jugadores[jugador_id]["x"]
                y = jugadores[jugador_id]["y"]
                cam_x = max(0, min(x - WIDTH//2, MAP_WIDTH - WIDTH))
                cam_y = max(0, min(y - HEIGHT//2, MAP_HEIGHT - HEIGHT))

        except socket.timeout:
            pass  # Continuar sin datos nuevos
        except Exception as e:
            if time.time() - last_network_time > 5:  # 5 segundos sin datos
                print(f"[CLIENTE] Perdida conexión con el servidor: {e}")
                break

        # Dibujar
        win.fill((40, 40, 40))

        # Dibujar mapa con patrón mejorado
        for gx in range(0, MAP_WIDTH, 100):
            if -100 <= gx - cam_x <= WIDTH + 100:
                color = (60,60,60) if (gx // 100) % 2 == 0 else (50,50,50)
                pygame.draw.line(win, color, (gx - cam_x, 0 - cam_y), (gx - cam_x, MAP_HEIGHT - cam_y))
        for gy in range(0, MAP_HEIGHT, 100):
            if -100 <= gy - cam_y <= HEIGHT + 100:
                color = (60,60,60) if (gy // 100) % 2 == 0 else (50,50,50)
                pygame.draw.line(win, color, (0 - cam_x, gy - cam_y), (MAP_WIDTH - cam_x, gy - cam_y))

        # Dibujar coordenadas optimizadas
        for gx in range(0, MAP_WIDTH, 200):  # Menos frecuentes
            if 0 <= gx - cam_x < WIDTH:
                text = font_small.render(str(gx), True, (150,150,150))
                win.blit(text, (gx - cam_x, 5))
        for gy in range(0, MAP_HEIGHT, 200):
            if 0 <= gy - cam_y < HEIGHT:
                text = font_small.render(str(gy), True, (150,150,150))
                win.blit(text, (5, gy - cam_y))

        # Dibujar vidas (health pickups) antes que los jugadores
        for pickup in health_pickups:
            px, py = int(pickup["x"] - cam_x), int(pickup["y"] - cam_y)
            # Solo dibujar si está visible en pantalla
            if -20 <= px <= WIDTH + 20 and -20 <= py <= HEIGHT + 20:
                # Círculo rojo con efecto pulsante
                pulse = int(5 + 3 * math.sin(time.time() * 4))  # Efecto pulsante
                # Círculo exterior (más claro)
                pygame.draw.circle(win, (255, 100, 100), (px, py), 15 + pulse // 2)
                # Círculo interior (más oscuro)
                pygame.draw.circle(win, (200, 50, 50), (px, py), 12)
                # Cruz blanca pequeña (símbolo médico)
                pygame.draw.line(win, (255, 255, 255), (px - 5, py), (px + 5, py), 2)
                pygame.draw.line(win, (255, 255, 255), (px, py - 5), (px, py + 5), 2)

        # Dibujar jugadores y balas con mejor renderizado
        for jid, j in jugadores.items():
            # Culling: solo dibujar si está visible
            if (j["x"] - cam_x < -50 or j["x"] - cam_x > WIDTH + 50 or
                j["y"] - cam_y < -50 or j["y"] - cam_y > HEIGHT + 50):
                continue

            # No dibujar el jugador local si es espectador
            if spectator and jid == jugador_id:
                continue

            # Dibujar jugador con borde si es el jugador local
            if jid == jugador_id and not spectator:
                pygame.draw.rect(win, (255,255,255), (j["x"] - cam_x - 2, j["y"] - cam_y - 2, 44, 44))
            pygame.draw.rect(win, j["color"], (j["x"] - cam_x, j["y"] - cam_y, 40, 40))

            # Balas con trail effect
            for b in j["balas"]:
                bx, by = int(b["x"] - cam_x), int(b["y"] - cam_y)
                if -10 <= bx <= WIDTH + 10 and -10 <= by <= HEIGHT + 10:
                    pygame.draw.circle(win, (255,255,100), (bx, by), 4)
                    pygame.draw.circle(win, (255,255,255), (bx, by), 2)

            # Barra de vida mejorada
            bar_width = 45
            bar_height = 6
            health_ratio = max(0, j["vida"] / 100)

            # Fondo de la barra
            pygame.draw.rect(win, (100,100,100), (j["x"]-cam_x-2, j["y"]-15-cam_y, bar_width, bar_height))
            # Barra de vida con colores graduales
            if health_ratio > 0.6:
                color = (0, 255, 0)
            elif health_ratio > 0.3:
                color = (255, 255, 0)
            else:
                color = (255, 0, 0)
            pygame.draw.rect(win, color, (j["x"]-cam_x, j["y"]-13-cam_y, int(bar_width * health_ratio)-4, bar_height-2))

        # Minimap
        minimap_w, minimap_h = 220, 165
        minimap_surface = pygame.Surface((minimap_w, minimap_h), pygame.SRCALPHA)
        minimap_surface.fill((20, 20, 20, 200))

        scale_x = (minimap_w - 20) / MAP_WIDTH
        scale_y = (minimap_h - 20) / MAP_HEIGHT

        # Dibujar vidas en el minimap
        for pickup in health_pickups:
            px = int(pickup["x"] * scale_x) + 10
            py = int(pickup["y"] * scale_y) + 10
            pygame.draw.circle(minimap_surface, (255, 100, 100), (px, py), 3)

        # Dibujar vista actual en minimap
        view_x = int(cam_x * scale_x) + 10
        view_y = int(cam_y * scale_y) + 10
        view_w = int(WIDTH * scale_x)
        view_h = int(HEIGHT * scale_y)
        pygame.draw.rect(minimap_surface, (100,100,100,100), (view_x, view_y, view_w, view_h), 2)

        # Jugadores en minimap
        for jid, j in jugadores.items():
            px = int(j["x"] * scale_x) + 10
            py = int(j["y"] * scale_y) + 10
            color = (0,255,255) if jid == jugador_id else j["color"]
            size = 8 if jid == jugador_id else 6
            pygame.draw.circle(minimap_surface, color, (px, py), size)
            if j.get("spectator", False):
                pygame.draw.circle(minimap_surface, (128,128,128), (px, py), size, 2)

        pygame.draw.rect(minimap_surface, (200,200,200), (0,0,minimap_w,minimap_h), 2)
        win.blit(minimap_surface, (WIDTH-minimap_w-10, HEIGHT-minimap_h-10))

        # UI mejorado
        ui_y = 10

        # FPS counter
        fps_text = font_small.render(f"FPS: {current_fps}", True, (200,200,200))
        win.blit(fps_text, (10, ui_y))
        ui_y += 25

        # Contador de jugadores
        total_players = len(jugadores)
        alive_players = sum(1 for j in jugadores.values() if not j.get("spectator", False))
        players_text = font_small.render(f"Jugadores: {alive_players}/{total_players}", True, (200,200,200))
        win.blit(players_text, (10, ui_y))
        ui_y += 25

        # Contador de vidas disponibles
        health_count_text = font_small.render(f"Vidas disponibles: {len(health_pickups)}", True, (255,100,100))
        win.blit(health_count_text, (10, ui_y))
        ui_y += 25

        # Estado de conexión
        if connection_lost:
            conn_text = font_small.render("Conexión perdida...", True, (255,100,100))
            win.blit(conn_text, (10, ui_y))
        elif time.time() - last_network_time > 2:
            conn_text = font_small.render("Lag detectado", True, (255,255,100))
            win.blit(conn_text, (10, ui_y))

        # Estadísticas del jugador
        if jugador_id in jugadores:
            j = jugadores[jugador_id]
            kills = j.get("kills", 0)
            deaths = j.get("deaths", 0)
            kd_ratio = kills / max(deaths, 1)
            stats_text = font_small.render(f"K/D: {kills}/{deaths} ({kd_ratio:.2f})", True, (200,200,200))
            win.blit(stats_text, (WIDTH - 180, 10))

        # Modo espectador con instrucciones
        if spectator:
            # Fondo semi-transparente
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((0,0,0,100))
            win.blit(overlay, (0,0))

            # Mensajes
            spectator_text = font_large.render("MODO ESPECTADOR", True, (255,255,255))
            win.blit(spectator_text, (WIDTH//2 - spectator_text.get_width()//2, HEIGHT//2 - 60))

            respawn_text = font_medium.render("Presiona R para reaparecer", True, (200,200,200))
            win.blit(respawn_text, (WIDTH//2 - respawn_text.get_width()//2, HEIGHT//2 - 20))

            controls_text = font_small.render("WASD: Mover cámara | Shift: Rápido", True, (150,150,150))
            win.blit(controls_text, (WIDTH//2 - controls_text.get_width()//2, HEIGHT//2 + 20))

        # Controles en pantalla (si no es espectador)
        elif not spectator:
            controls = [
                "WASD: Movimiento | Shift: Correr",
                "Click: Disparar | Delete: Suicidio"
            ]
            for i, control in enumerate(controls):
                text = font_small.render(control, True, (120,120,120))
                win.blit(text, (10, HEIGHT - 50 + i * 20))

        pygame.display.update()

    pygame.quit()
    if client:
        client.close()

if __name__ == "__main__":
    main()
