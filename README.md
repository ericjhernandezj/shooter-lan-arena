# Shooter LAN - Arena

A simple top-down multiplayer shooter game built with Python and Pygame. Players compete in a large arena, collect health pickups, and try to outlast each other.

## Features

- Multiplayer over LAN (local network)
- Health pickups spawn dynamically based on player count
- Spectator mode after death, with respawn option
- Minimap and player stats display

## Requirements

- Python 3.8+
- Pygame
- (Optional) Run both server and clients on the same or different machines in the same network

## Installation

1. Clone this repository.
2. Install dependencies:
   ```
   pip install pygame
   ```

## How to Play

1. **Start the server:**
   ```
   python server.py
   ```
   The server will listen on port 5555.

2. **Start the client(s):**
   ```
   python client.py
   ```
   By default, the client connects to `127.0.0.1` (localhost). To connect to a remote server, change the IP in `client.py`.

3. **Controls:**
   - `WASD` or arrow keys: Move
   - `Shift`: Sprint
   - `Mouse click`: Shoot
   - `Delete`: Suicide
   - `R`: Respawn (in spectator mode)

## Notes

- Health pickups (red circles) restore 10 health, but only if you are not at full health.
- The number of health pickups matches the number of active players.
- If you die, you enter spectator mode and can respawn with `R`.

## License

MIT License

