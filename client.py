import pygame
import socket
import pickle
import math
import time

from server import players

# Client config
WIDTH, HEIGHT = 800, 600          # Window
MAP_WIDTH, MAP_HEIGHT = 2000, 2000  # Map
FPS = 60

def connect():
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.settimeout(10)  # Timeout for connection attempt
    try:
        client.connect(("127.0.0.1", 5555))
#        client.connect(("192.168.184.20", 5555))
        client.settimeout(None)  # Remove timeout after connection
        return client
    except socket.timeout:
        print("[CLIENT] Timeout connecting to server")
        return None
    except Exception as e:
        print(f"[CLIENT] Error connecting: {e}")
        return None

def main():
    pygame.init()
    win = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Shooter LAN - Arena")
    clock = pygame.time.Clock()

    # Fonts
    font_small = pygame.font.SysFont(None, 24)
    font_medium = pygame.font.SysFont(None, 32)
    font_large = pygame.font.SysFont(None, 48)

    client = connect()
    if not client:
        print("[CLIENT] Cannot connect to server")
        return

    # Receive player ID from server
    try:
        client.settimeout(5)
        player_id = pickle.loads(client.recv(1024))
        client.settimeout(None)
        print(f"[CLIENT] Connected with ID {player_id}")
    except Exception as e:
        print(f"[CLIENT] Error receiving ID from server: {e}")
        return

    # Initial states
    spectator = False
    cam_x, cam_y = 0, 0
    players = {}
    health_pickups = []  # Initialize health pickups list
    last_network_time = time.time()
    connection_lost = False

    # Performance metrics
    fps_counter = 0
    fps_time = time.time()
    current_fps = 0

    run = True
    while run:
        clock.tick(FPS)
        fps_counter += 1

        # Calculate FPS every second
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
                # In spectator mode, listen for respawn key
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
            # Camera movement in spectator mode
            speed = 15 if keys[pygame.K_LSHIFT] else 10
            if keys[pygame.K_a] or keys[pygame.K_LEFT]: cam_x -= speed
            if keys[pygame.K_d] or keys[pygame.K_RIGHT]: cam_x += speed
            if keys[pygame.K_w] or keys[pygame.K_UP]: cam_y -= speed
            if keys[pygame.K_s] or keys[pygame.K_DOWN]: cam_y += speed
            cam_x = max(0, min(cam_x, MAP_WIDTH - WIDTH))
            cam_y = max(0, min(cam_y, MAP_HEIGHT - HEIGHT))

        # Send input to server
        try:
            input_data = {"move": move, "shoot": shoot, "sprint": sprint, "respawn": respawn}
            client.sendall(pickle.dumps(input_data))
            connection_lost = False
        except Exception as e:
            if not connection_lost:
                print(f"[CLIENT] Error sending data: {e}")
                connection_lost = True

        # Receive game state from server
        try:
            client.settimeout(0.1)  # Short timeout for receiving
            data = client.recv(16384)
            client.settimeout(None)

            if not data:
                print("[CLIENT] Server closed connection")
                break

            state = pickle.loads(data)
            players = state["players"]
            spectator = state.get("spectator", False)
            health_pickups = state.get("health_pickups", [])  # Receive health pickups
            last_network_time = time.time()

            # Update camera to follow player if not spectator
            if not spectator and player_id in players:
                x = players[player_id]["x"]
                y = players[player_id]["y"]
                cam_x = max(0, min(x - WIDTH//2, MAP_WIDTH - WIDTH))
                cam_y = max(0, min(y - HEIGHT//2, MAP_HEIGHT - HEIGHT))

        except socket.timeout:
            pass  # Continue if no data received
        except Exception as e:
            if time.time() - last_network_time > 5:  # 5 segundos sin datos
                print(f"[CLIENT] Connection lost: {e}")
                break

        # Drawing
        win.fill((40, 40, 40))

        # Draw grid optimized
        for gx in range(0, MAP_WIDTH, 100):
            if -100 <= gx - cam_x <= WIDTH + 100:
                color = (60,60,60) if (gx // 100) % 2 == 0 else (50,50,50)
                pygame.draw.line(win, color, (gx - cam_x, 0 - cam_y), (gx - cam_x, MAP_HEIGHT - cam_y))
        for gy in range(0, MAP_HEIGHT, 100):
            if -100 <= gy - cam_y <= HEIGHT + 100:
                color = (60,60,60) if (gy // 100) % 2 == 0 else (50,50,50)
                pygame.draw.line(win, color, (0 - cam_x, gy - cam_y), (MAP_WIDTH - cam_x, gy - cam_y))

        # Draw grid coordinates less frequently
        for gx in range(0, MAP_WIDTH, 200):  # Less frequent
            if 0 <= gx - cam_x < WIDTH:
                text = font_small.render(str(gx), True, (150,150,150))
                win.blit(text, (gx - cam_x, 5))
        for gy in range(0, MAP_HEIGHT, 200):
            if 0 <= gy - cam_y < HEIGHT:
                text = font_small.render(str(gy), True, (150,150,150))
                win.blit(text, (5, gy - cam_y))

        # Draw health pickups with pulsating effect and better visibility
        for pickup in health_pickups:
            px, py = int(pickup["x"] - cam_x), int(pickup["y"] - cam_y)
            # Only draw if within view
            if -20 <= px <= WIDTH + 20 and -20 <= py <= HEIGHT + 20:
                # Red circle with white cross
                pulse = int(5 + 3 * math.sin(time.time() * 4))  # Pulsating effect
                # Exterior glow
                pygame.draw.circle(win, (255, 100, 100), (px, py), 15 + pulse // 2)
                # Interior circle
                pygame.draw.circle(win, (200, 50, 50), (px, py), 12)
                # Small white cross
                pygame.draw.line(win, (255, 255, 255), (px - 5, py), (px + 5, py), 2)
                pygame.draw.line(win, (255, 255, 255), (px, py - 5), (px, py + 5), 2)

        # Draw players
        for pid, p in players.items():
            # Culling: only draw if within or near view
            if (p["x"] - cam_x < -50 or p["x"] - cam_x > WIDTH + 50 or
                p["y"] - cam_y < -50 or p["y"] - cam_y > HEIGHT + 50):
                continue

            # Don't draw local player if spectator
            if spectator and pid == player_id:
                continue

            # Draw player with outline if local player
            if pid == player_id and not spectator:
                pygame.draw.rect(win, (255,255,255), (p["x"] - cam_x - 2, p["y"] - cam_y - 2, 44, 44))
            pygame.draw.rect(win, p["color"], (p["x"] - cam_x, p["y"] - cam_y, 40, 40))

            # Bullets with culling
            for b in p["bullets"]:
                bx, by = int(b["x"] - cam_x), int(b["y"] - cam_y)
                if -10 <= bx <= WIDTH + 10 and -10 <= by <= HEIGHT + 10:
                    pygame.draw.circle(win, (255,255,100), (bx, by), 4)
                    pygame.draw.circle(win, (255,255,255), (bx, by), 2)

            # Health bar with gradient color
            bar_width = 45
            bar_height = 6
            health_ratio = max(0, p["health"] / 100)

            # Health bar background
            pygame.draw.rect(win, (100,100,100), (p["x"]-cam_x-2, p["y"]-15-cam_y, bar_width, bar_height))
            # Health bar foreground with gradient
            if health_ratio > 0.6:
                color = (0, 255, 0)
            elif health_ratio > 0.3:
                color = (255, 255, 0)
            else:
                color = (255, 0, 0)
            pygame.draw.rect(win, color, (p["x"]-cam_x, p["y"]-13-cam_y, int(bar_width * health_ratio)-4, bar_height-2))

        # Minimap
        minimap_w, minimap_h = 220, 165
        minimap_surface = pygame.Surface((minimap_w, minimap_h), pygame.SRCALPHA)
        minimap_surface.fill((20, 20, 20, 200))

        scale_x = (minimap_w - 20) / MAP_WIDTH
        scale_y = (minimap_h - 20) / MAP_HEIGHT

        # Draw health pickups on minimap
        for pickup in health_pickups:
            px = int(pickup["x"] * scale_x) + 10
            py = int(pickup["y"] * scale_y) + 10
            pygame.draw.circle(minimap_surface, (255, 100, 100), (px, py), 3)

        # Draw camera view rectangle
        view_x = int(cam_x * scale_x) + 10
        view_y = int(cam_y * scale_y) + 10
        view_w = int(WIDTH * scale_x)
        view_h = int(HEIGHT * scale_y)
        pygame.draw.rect(minimap_surface, (100,100,100,100), (view_x, view_y, view_w, view_h), 2)

        # Players on minimap
        for pid, p in players.items():
            px = int(p["x"] * scale_x) + 10
            py = int(p["y"] * scale_y) + 10
            color = (0,255,255) if pid == player_id else p["color"]
            size = 8 if pid == player_id else 6
            pygame.draw.circle(minimap_surface, color, (px, py), size)
            if p.get("spectator", False):
                pygame.draw.circle(minimap_surface, (128,128,128), (px, py), size, 2)

        pygame.draw.rect(minimap_surface, (200,200,200), (0,0,minimap_w,minimap_h), 2)
        win.blit(minimap_surface, (WIDTH-minimap_w-10, HEIGHT-minimap_h-10))

        # Better organized UI
        ui_y = 10

        # FPS counter
        fps_text = font_small.render(f"FPS: {current_fps}", True, (200,200,200))
        win.blit(fps_text, (10, ui_y))
        ui_y += 25

        # Player count
        total_players = len(players)
        alive_players = sum(1 for j in players.values() if not j.get("spectator", False))
        players_text = font_small.render(f"Players: {alive_players}/{total_players}", True, (200,200,200))
        win.blit(players_text, (10, ui_y))
        ui_y += 25

        # Available health pickups
        health_count_text = font_small.render(f"Available health pickups: {len(health_pickups)}", True, (255,100,100))
        win.blit(health_count_text, (10, ui_y))
        ui_y += 25

        # State of connection
        if connection_lost:
            conn_text = font_small.render("Lost connection...", True, (255,100,100))
            win.blit(conn_text, (10, ui_y))
        elif time.time() - last_network_time > 2:
            conn_text = font_small.render("Lag detected", True, (255,255,100))
            win.blit(conn_text, (10, ui_y))

        # Player stats
        if player_id in players:
            p = players[player_id]
            kills = p.get("kills", 0)
            deaths = p.get("deaths", 0)
            kd_ratio = kills / max(deaths, 1)
            stats_text = font_small.render(f"K/D: {kills}/{deaths} ({kd_ratio:.2f})", True, (200,200,200))
            win.blit(stats_text, (WIDTH - 180, 10))

        # Spectator mode overlay
        if spectator:
            # Semi-transparent overlay
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((0,0,0,100))
            win.blit(overlay, (0,0))

            # Messages
            spectator_text = font_large.render("SPECTATOR MODE", True, (255,255,255))
            win.blit(spectator_text, (WIDTH//2 - spectator_text.get_width()//2, HEIGHT//2 - 60))

            respawn_text = font_medium.render("Press R to respawn", True, (200,200,200))
            win.blit(respawn_text, (WIDTH//2 - respawn_text.get_width()//2, HEIGHT//2 - 20))

            controls_text = font_small.render("WASD: Move camera | Shift: Sprint", True, (150,150,150))
            win.blit(controls_text, (WIDTH//2 - controls_text.get_width()//2, HEIGHT//2 + 20))

        # Control hints
        elif not spectator:
            controls = [
                "WASD: Movement | Shift: Sprint",
                "Click: Shoot | Delete: Suicide"
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
