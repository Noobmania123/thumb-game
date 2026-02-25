import argparse
import json
import math
import socket
import sys
import time
from dataclasses import dataclass

import pygame

# --- Game tuning constants ---
SCREEN_WIDTH = 960
SCREEN_HEIGHT = 540
FPS = 60
ROAD_WIDTH = 2200
SEGMENT_LENGTH = 200
DRAW_DISTANCE = 220
CAMERA_HEIGHT = 1000
CAMERA_DEPTH = 0.84
MAX_SPEED = SEGMENT_LENGTH / (1 / FPS) * 0.9
ACCEL = MAX_SPEED / 5.6
BRAKING = -MAX_SPEED / 3.0
DECEL = -MAX_SPEED / 8
TRACK_LENGTH = 1600
RACE_LAPS = 3

WALL_LIMIT = 0.95
WALL_BOUNCE = 0.45
CRASH_COOLDOWN = 0.9

MODE_ORDER = ["single", "local", "online-host", "online-join"]


@dataclass
class Segment:
    index: int
    curve: float = 0.0
    y: float = 0.0


@dataclass
class PlayerState:
    name: str
    position: float = 0.0
    speed: float = 0.0
    x: float = 0.0
    lap: int = 0
    crashed_until: float = 0.0
    car_color: tuple[int, int, int] = (230, 40, 50)


@dataclass
class RaceState:
    enabled: bool = True
    countdown_end: float = 0.0
    finished: bool = False
    winner: str = ""


class NetSession:
    def __init__(self, mode: str, host: str, port: int) -> None:
        self.mode = mode
        self.sock: socket.socket | None = None
        self.remote_addr: tuple[str, int] | None = None
        self.last_remote: dict[str, float] = {"position": 0.0, "speed": 0.0, "x": 0.0, "lap": 0.0}
        self.connected = False

        if mode not in {"online-host", "online-join"}:
            return

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setblocking(False)
        if mode == "online-host":
            self.sock.bind(("0.0.0.0", port))
        else:
            self.remote_addr = (host, port)

    def tick(self, payload: dict[str, float]) -> None:
        if not self.sock:
            return

        packet = json.dumps(payload).encode("utf-8")
        if self.remote_addr:
            self.sock.sendto(packet, self.remote_addr)

        for _ in range(8):
            try:
                data, addr = self.sock.recvfrom(2048)
            except BlockingIOError:
                break

            if self.mode == "online-host" and self.remote_addr is None:
                self.remote_addr = addr

            if self.remote_addr and addr != self.remote_addr:
                continue

            try:
                incoming = json.loads(data.decode("utf-8"))
            except json.JSONDecodeError:
                continue

            self.last_remote = {
                "position": float(incoming.get("position", 0.0)),
                "speed": float(incoming.get("speed", 0.0)),
                "x": float(incoming.get("x", 0.0)),
                "lap": float(incoming.get("lap", 0.0)),
            }
            self.connected = True

    def close(self) -> None:
        if self.sock:
            self.sock.close()


def build_track() -> list[Segment]:
    """Build a race-oriented track with clear turn sections and straights."""
    track: list[Segment] = [Segment(i) for i in range(TRACK_LENGTH)]

    def add_section(start: int, length: int, curve: float, hill: float) -> int:
        for i in range(length):
            idx = (start + i) % TRACK_LENGTH
            p = i / max(1, length - 1)
            smooth = (1 - math.cos(p * math.pi)) / 2
            track[idx].curve = curve * smooth
            track[idx].y = hill * smooth
        return (start + length) % TRACK_LENGTH

    cursor = 0
    pattern = [
        (180, 0.0, 0),
        (90, 0.9, 40),
        (80, 1.25, 30),
        (120, 0.0, -30),
        (110, -1.15, -50),
        (90, -0.9, 20),
        (200, 0.0, 0),
        (100, 1.45, 70),
        (120, 0.0, 40),
        (140, -1.3, -70),
        (140, 0.0, 0),
    ]

    while cursor < TRACK_LENGTH:
        for length, curve, hill in pattern:
            if cursor >= TRACK_LENGTH:
                break
            real_len = min(length, TRACK_LENGTH - cursor)
            cursor = add_section(cursor, real_len, curve, hill)

    return track


def project(world_x: float, world_y: float, world_z: float, camera_x: float, camera_y: float, camera_z: float) -> tuple[float, float, float]:
    dz = world_z - camera_z
    scale = CAMERA_DEPTH / dz if dz != 0 else 0.0001
    x = (1 + scale * (world_x - camera_x)) * SCREEN_WIDTH / 2
    y = (1 - scale * (world_y - camera_y)) * SCREEN_HEIGHT / 2
    w = scale * ROAD_WIDTH * SCREEN_WIDTH / 2
    return x, y, w


def draw_background(surface: pygame.Surface, speed_percent: float) -> None:
    horizon = SCREEN_HEIGHT * 0.45
    pygame.draw.rect(surface, (111, 180, 255), pygame.Rect(0, 0, SCREEN_WIDTH, int(horizon)))
    pygame.draw.rect(surface, (90, 180, 80), pygame.Rect(0, int(horizon), SCREEN_WIDTH, SCREEN_HEIGHT - int(horizon)))

    offset = int(pygame.time.get_ticks() * (0.02 + speed_percent * 0.06)) % SCREEN_WIDTH
    for i in range(-1, 4):
        x = i * 340 - offset
        pygame.draw.ellipse(surface, (220, 240, 255), pygame.Rect(x, 50, 220, 60))


def draw_segment(surface: pygame.Surface, x1: float, y1: float, w1: float, x2: float, y2: float, w2: float, dark: bool) -> None:
    if y2 >= y1:
        return

    road_col = (57, 57, 57) if dark else (66, 66, 66)
    rumble_col = (220, 40, 40) if dark else (240, 240, 240)

    pygame.draw.polygon(surface, (80, 160, 70), [(0, y2), (SCREEN_WIDTH, y2), (SCREEN_WIDTH, y1), (0, y1)])

    rumble1 = w1 * 1.15
    rumble2 = w2 * 1.15
    pygame.draw.polygon(surface, rumble_col, [(x1 - rumble1, y1), (x1 - w1, y1), (x2 - w2, y2), (x2 - rumble2, y2)])
    pygame.draw.polygon(surface, rumble_col, [(x1 + w1, y1), (x1 + rumble1, y1), (x2 + rumble2, y2), (x2 + w2, y2)])
    pygame.draw.polygon(surface, road_col, [(x1 - w1, y1), (x1 + w1, y1), (x2 + w2, y2), (x2 - w2, y2)])

    lane_w1 = w1 * 0.03
    lane_w2 = w2 * 0.03
    pygame.draw.polygon(surface, (240, 240, 160), [(x1 - lane_w1, y1), (x1 + lane_w1, y1), (x2 + lane_w2, y2), (x2 - lane_w2, y2)])

    # Solid walls with top cap for stronger racetrack feel.
    wall_h1 = w1 * 0.15
    wall_h2 = w2 * 0.15
    left_wall = [(x1 - w1 * WALL_LIMIT, y1), (x1 - w1 * WALL_LIMIT, y1 - wall_h1), (x2 - w2 * WALL_LIMIT, y2 - wall_h2), (x2 - w2 * WALL_LIMIT, y2)]
    right_wall = [(x1 + w1 * WALL_LIMIT, y1), (x1 + w1 * WALL_LIMIT, y1 - wall_h1), (x2 + w2 * WALL_LIMIT, y2 - wall_h2), (x2 + w2 * WALL_LIMIT, y2)]
    pygame.draw.polygon(surface, (165, 165, 180), left_wall)
    pygame.draw.polygon(surface, (165, 165, 180), right_wall)
    pygame.draw.polygon(surface, (215, 215, 225), [(x1 - w1 * WALL_LIMIT, y1 - wall_h1), (x1 - w1 * WALL_LIMIT + w1 * 0.03, y1 - wall_h1), (x2 - w2 * WALL_LIMIT + w2 * 0.03, y2 - wall_h2), (x2 - w2 * WALL_LIMIT, y2 - wall_h2)])
    pygame.draw.polygon(surface, (215, 215, 225), [(x1 + w1 * WALL_LIMIT - w1 * 0.03, y1 - wall_h1), (x1 + w1 * WALL_LIMIT, y1 - wall_h1), (x2 + w2 * WALL_LIMIT, y2 - wall_h2), (x2 + w2 * WALL_LIMIT - w2 * 0.03, y2 - wall_h2)])


def draw_player_car(surface: pygame.Surface, player: PlayerState, speed_percent: float, crashed: bool, x_offset: int = 0) -> None:
    base_y = SCREEN_HEIGHT - 80
    center_x = SCREEN_WIDTH // 2 + int(player.x * SCREEN_WIDTH * 0.35) + x_offset
    bob = int(math.sin(pygame.time.get_ticks() * 0.02) * (2 + speed_percent * 6))
    color = (255, 180, 30) if crashed else player.car_color

    pygame.draw.rect(surface, (20, 20, 20), pygame.Rect(center_x - 40, base_y + 6 + bob, 12, 16))
    pygame.draw.rect(surface, (20, 20, 20), pygame.Rect(center_x + 28, base_y + 6 + bob, 12, 16))
    pygame.draw.rect(surface, color, pygame.Rect(center_x - 34, base_y - 20 + bob, 68, 34), border_radius=5)
    pygame.draw.rect(surface, (200, 225, 245), pygame.Rect(center_x - 20, base_y - 38 + bob, 40, 18), border_radius=4)


def draw_remote_marker(surface: pygame.Surface, rel_z: float, rel_x: float, color: tuple[int, int, int]) -> None:
    if rel_z <= 0 or rel_z > DRAW_DISTANCE * SEGMENT_LENGTH:
        return
    scale = CAMERA_DEPTH / rel_z
    marker_x = int((1 + scale * (rel_x * ROAD_WIDTH)) * SCREEN_WIDTH / 2)
    marker_y = int((1 - scale * (-180)) * SCREEN_HEIGHT / 2)
    size = max(8, int(scale * 420))
    pygame.draw.rect(surface, color, pygame.Rect(marker_x - size // 2, marker_y - size, size, size), border_radius=3)


def wrap_distance(a: float, b: float) -> float:
    total = TRACK_LENGTH * SEGMENT_LENGTH
    d = (a - b) % total
    if d > total / 2:
        d -= total
    return d


def handle_crash(player: PlayerState, now: float) -> bool:
    if abs(player.x) <= WALL_LIMIT:
        return False
    player.x = max(-WALL_LIMIT, min(WALL_LIMIT, player.x))
    player.speed *= WALL_BOUNCE
    player.crashed_until = now + CRASH_COOLDOWN
    return True


def update_player(
    player: PlayerState,
    dt: float,
    steer_left: bool,
    steer_right: bool,
    accelerate: bool,
    brake: bool,
    now: float,
    can_drive: bool,
) -> bool:
    accel = DECEL
    if can_drive:
        if accelerate:
            accel = ACCEL
        elif brake:
            accel = BRAKING

    if now < player.crashed_until:
        accel = min(accel, DECEL)

    if steer_left:
        player.x -= 2.3 * dt * (player.speed / MAX_SPEED + 0.3)
    if steer_right:
        player.x += 2.3 * dt * (player.speed / MAX_SPEED + 0.3)

    player.speed = max(0.0, min(MAX_SPEED, player.speed + accel * dt))
    crashed = handle_crash(player, now)

    total = TRACK_LENGTH * SEGMENT_LENGTH
    prev = player.position
    player.position = (player.position + player.speed * dt) % total
    if player.position < prev and player.speed > 0:
        player.lap += 1
    return crashed


def render_world(surface: pygame.Surface, track: list[Segment], camera_player: PlayerState, remote_player: PlayerState | None) -> None:
    speed_percent = camera_player.speed / MAX_SPEED if MAX_SPEED else 0.0
    draw_background(surface, speed_percent)

    base_segment = int(camera_player.position // SEGMENT_LENGTH) % TRACK_LENGTH
    max_y = SCREEN_HEIGHT
    x = 0.0
    dx = 0.0

    for n in range(DRAW_DISTANCE):
        idx = (base_segment + n) % TRACK_LENGTH
        seg = track[idx]
        next_seg = track[(idx + 1) % TRACK_LENGTH]

        z1 = n * SEGMENT_LENGTH
        z2 = (n + 1) * SEGMENT_LENGTH

        x1, y1, w1 = project(x, seg.y, z1, camera_player.x * ROAD_WIDTH, CAMERA_HEIGHT, 0)
        x += dx
        dx += seg.curve * 0.03
        x2, y2, w2 = project(x, next_seg.y, z2, camera_player.x * ROAD_WIDTH, CAMERA_HEIGHT, 0)

        if y2 >= max_y:
            continue
        max_y = y2
        draw_segment(surface, x1, y1, w1, x2, y2, w2, (idx // 3) % 2 == 0)

    if remote_player:
        draw_remote_marker(surface, wrap_distance(remote_player.position, camera_player.position), remote_player.x - camera_player.x, remote_player.car_color)


def mode_label(mode: str) -> str:
    return {
        "single": "Single Player",
        "local": "Local Multiplayer",
        "online-host": "Online Host",
        "online-join": "Online Client",
    }[mode]


def cycle_mode(current: str, direction: int = 1) -> str:
    idx = MODE_ORDER.index(current)
    return MODE_ORDER[(idx + direction) % len(MODE_ORDER)]


def init_mode(mode: str, host: str, port: int, race_enabled: bool) -> tuple[PlayerState, PlayerState, NetSession, RaceState]:
    p1 = PlayerState(name="P1", car_color=(230, 40, 50), x=-0.2)
    p2 = PlayerState(name="P2", car_color=(40, 160, 255), x=0.2)
    net = NetSession(mode, host, port)
    race = RaceState(enabled=race_enabled, countdown_end=time.perf_counter() + 3.0)
    return p1, p2, net, race


def check_race_finish(race: RaceState, p1: PlayerState, p2: PlayerState, mode: str) -> None:
    if not race.enabled or race.finished:
        return
    if p1.lap >= RACE_LAPS:
        race.finished = True
        race.winner = p1.name
    elif mode == "local" and p2.lap >= RACE_LAPS:
        race.finished = True
        race.winner = p2.name


def run(mode: str, host: str, port: int, race_enabled: bool) -> None:
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("Thumb Drive Racer")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("consolas", 20)
    big_font = pygame.font.SysFont("consolas", 40, bold=True)

    track = build_track()
    player1, player2, net, race = init_mode(mode, host, port, race_enabled)

    running = True
    while running:
        dt = clock.tick(FPS) / 1000
        now = time.perf_counter()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_TAB:
                    mode = cycle_mode(mode)
                    net.close()
                    player1, player2, net, race = init_mode(mode, host, port, race.enabled)
                elif event.key == pygame.K_F1:
                    mode = "single"
                    net.close()
                    player1, player2, net, race = init_mode(mode, host, port, race.enabled)
                elif event.key == pygame.K_F2:
                    mode = "local"
                    net.close()
                    player1, player2, net, race = init_mode(mode, host, port, race.enabled)
                elif event.key == pygame.K_F3:
                    mode = "online-host"
                    net.close()
                    player1, player2, net, race = init_mode(mode, host, port, race.enabled)
                elif event.key == pygame.K_F4:
                    mode = "online-join"
                    net.close()
                    player1, player2, net, race = init_mode(mode, host, port, race.enabled)
                elif event.key == pygame.K_r:
                    race.enabled = not race.enabled
                    player1, player2, net, race = init_mode(mode, host, port, race.enabled)

        keys = pygame.key.get_pressed()
        race_started = not race.enabled or now >= race.countdown_end
        race_finished = race.enabled and race.finished
        can_drive = race_started and not race_finished

        crash1 = update_player(
            player1,
            dt,
            steer_left=keys[pygame.K_a] or keys[pygame.K_LEFT],
            steer_right=keys[pygame.K_d] or keys[pygame.K_RIGHT],
            accelerate=keys[pygame.K_w] or keys[pygame.K_UP],
            brake=keys[pygame.K_s] or keys[pygame.K_DOWN],
            now=now,
            can_drive=can_drive,
        )

        crash2 = False
        if mode == "local":
            crash2 = update_player(
                player2,
                dt,
                steer_left=keys[pygame.K_j],
                steer_right=keys[pygame.K_l],
                accelerate=keys[pygame.K_i],
                brake=keys[pygame.K_k],
                now=now,
                can_drive=can_drive,
            )
        elif mode in {"online-host", "online-join"}:
            net.tick({"position": player1.position, "speed": player1.speed, "x": player1.x, "lap": float(player1.lap)})
            player2.position = net.last_remote["position"]
            player2.speed = net.last_remote["speed"]
            player2.x = net.last_remote["x"]
            player2.lap = int(net.last_remote["lap"])

        check_race_finish(race, player1, player2, mode)

        render_world(screen, track, player1, player2 if mode != "single" else None)
        draw_player_car(screen, player1, player1.speed / MAX_SPEED, now < player1.crashed_until)
        if mode == "local":
            draw_player_car(screen, player2, player2.speed / MAX_SPEED, now < player2.crashed_until, x_offset=220)

        hud_lines = [
            f"Mode: {mode_label(mode)}  (TAB cycle | F1-F4 quick switch)",
            f"P1 Speed: {int(player1.speed * 0.15):03d} km/h  Lap: {player1.lap}/{RACE_LAPS if race.enabled else '-'}",
            "Race Mode: ON (R toggle)" if race.enabled else "Race Mode: OFF (R toggle)",
        ]

        if mode == "local":
            hud_lines.append(f"P2 Speed: {int(player2.speed * 0.15):03d} km/h  Lap: {player2.lap}/{RACE_LAPS if race.enabled else '-'}")
            hud_lines.append("P2 Controls: I/K accel-brake, J/L steer")

        if mode in {"online-host", "online-join"}:
            hud_lines.append(f"Network: {'connected' if net.connected else 'waiting'} ({host}:{port})")

        if crash1 or crash2:
            hud_lines.append("CRASH! Wall hit -> speed reduced")

        for i, line in enumerate(hud_lines):
            screen.blit(font.render(line, True, (255, 255, 255)), (14, 14 + i * 23))

        if race.enabled and not race.finished and now < race.countdown_end:
            countdown = max(1, int(math.ceil(race.countdown_end - now)))
            label = big_font.render(str(countdown), True, (255, 230, 80))
            screen.blit(label, (SCREEN_WIDTH // 2 - label.get_width() // 2, 90))
        elif race.enabled and race.finished:
            text = big_font.render(f"{race.winner} Wins! Press R to restart race", True, (255, 230, 80))
            screen.blit(text, (SCREEN_WIDTH // 2 - text.get_width() // 2, 90))

        screen.blit(font.render("P1 Controls: WASD/Arrows", True, (255, 255, 255)), (14, SCREEN_HEIGHT - 32))

        pygame.display.flip()

    net.close()
    pygame.quit()
    sys.exit(0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Thumb Drive Racer")
    parser.add_argument("--mode", choices=MODE_ORDER, default="single", help="Initial game mode")
    parser.add_argument("--host", default="127.0.0.1", help="Host IP for online modes")
    parser.add_argument("--port", type=int, default=50555, help="UDP port for online modes")
    parser.add_argument("--race", action="store_true", help="Start with race mode enabled")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run(args.mode, args.host, args.port, args.race)
