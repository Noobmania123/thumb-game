import argparse
import json
import math
import os
import socket
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

# Prefer software rendering on older/low-power GPUs to avoid black-screen GPU driver issues.
os.environ.setdefault("SDL_RENDER_DRIVER", "software")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

# --- Base tuning constants ---
ROAD_WIDTH = 2200
SEGMENT_LENGTH = 200
CAMERA_HEIGHT = 1000
CAMERA_DEPTH = 0.84
TRACK_LENGTH = 1600
RACE_LAPS = 3

WALL_LIMIT = 0.95
WALL_BOUNCE = 0.45
CRASH_COOLDOWN = 0.9
EXPLOSION_SPEED_THRESHOLD = 0.62  # percentage of MAX_SPEED
MAX_DISPLAY_KMH = 300

MODE_ORDER = ["single", "local", "online-host", "online-join"]
PERF_ORDER = ["ultra-low", "low", "normal"]

# Runtime settings (set by performance profile)
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 450
FPS = 45
DRAW_DISTANCE = 90
CLOUD_LAYERS = 1
MAX_SPEED = 0.0
ACCEL = 0.0
BRAKING = 0.0
DECEL = 0.0
KMH_FACTOR = 0.0

TRACK_PATTERN = [
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

P1_COLOR = (230, 40, 50)
P2_COLOR = (40, 160, 255)
WALL_COLOR = (210, 210, 225)
TREE_TRUNK_COLOR = (92, 58, 34)
TREE_CROWN_COLOR = (34, 126, 42)
ROAD_DARK_COLOR = (58, 58, 58)
ROAD_LIGHT_COLOR = (68, 68, 68)
MOD_NAME = "Vanilla"


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
    out_of_action: bool = False
    exploded: bool = False
    heading: float = 0.0
    x_velocity: float = 0.0


@dataclass
class RaceState:
    enabled: bool = True
    countdown_end: float = 0.0
    finished: bool = False
    winner: str = ""


@dataclass
class LoadingUI:
    font_title: pygame.font.Font
    font_small: pygame.font.Font
    last_percent: int = -1

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


def parse_color(value: object, fallback: tuple[int, int, int]) -> tuple[int, int, int]:
    if not isinstance(value, list) or len(value) != 3:
        return fallback
    channels: list[int] = []
    for channel in value:
        if not isinstance(channel, int):
            return fallback
        channels.append(max(0, min(255, channel)))
    return (channels[0], channels[1], channels[2])


def parse_track_pattern(value: object) -> list[tuple[int, float, float]] | None:
    if not isinstance(value, list) or not value:
        return None

    parsed: list[tuple[int, float, float]] = []
    for entry in value:
        if not isinstance(entry, dict):
            return None
        length = entry.get("length")
        curve = entry.get("curve", 0.0)
        hill = entry.get("hill", 0.0)
        if not isinstance(length, int) or length <= 0:
            return None
        if not isinstance(curve, (int, float)) or not isinstance(hill, (int, float)):
            return None
        parsed.append((max(10, min(400, length)), float(curve), float(hill)))
    return parsed


def load_mod(path: str | None) -> str:
    """Load a simple JSON mod and apply supported gameplay/visual overrides."""
    global MOD_NAME, P1_COLOR, P2_COLOR, WALL_COLOR, TREE_TRUNK_COLOR, TREE_CROWN_COLOR
    global ROAD_DARK_COLOR, ROAD_LIGHT_COLOR, MAX_DISPLAY_KMH, EXPLOSION_SPEED_THRESHOLD
    global RACE_LAPS, TRACK_PATTERN

    if not path:
        recalc_physics()
        return MOD_NAME

    mod_path = Path(path)
    with mod_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError("Mod file root must be a JSON object")

    MOD_NAME = str(data.get("name", mod_path.stem))

    gameplay = data.get("gameplay", {})
    if isinstance(gameplay, dict):
        max_kmh = gameplay.get("max_display_kmh")
        if isinstance(max_kmh, (int, float)):
            MAX_DISPLAY_KMH = int(max(80, min(600, max_kmh)))
        threshold = gameplay.get("explosion_speed_threshold")
        if isinstance(threshold, (int, float)):
            EXPLOSION_SPEED_THRESHOLD = max(0.1, min(0.95, float(threshold)))
        laps = gameplay.get("race_laps")
        if isinstance(laps, int):
            RACE_LAPS = max(1, min(20, laps))

    colors = data.get("colors", {})
    if isinstance(colors, dict):
        P1_COLOR = parse_color(colors.get("player1"), P1_COLOR)
        P2_COLOR = parse_color(colors.get("player2"), P2_COLOR)
        WALL_COLOR = parse_color(colors.get("walls"), WALL_COLOR)
        TREE_TRUNK_COLOR = parse_color(colors.get("tree_trunk"), TREE_TRUNK_COLOR)
        TREE_CROWN_COLOR = parse_color(colors.get("tree_crown"), TREE_CROWN_COLOR)
        ROAD_DARK_COLOR = parse_color(colors.get("road_dark"), ROAD_DARK_COLOR)
        ROAD_LIGHT_COLOR = parse_color(colors.get("road_light"), ROAD_LIGHT_COLOR)

    track = data.get("track", {})
    if isinstance(track, dict):
        pattern = parse_track_pattern(track.get("pattern"))
        if pattern:
            TRACK_PATTERN = pattern

    recalc_physics()
    return MOD_NAME


def recalc_physics() -> None:
    global MAX_SPEED, ACCEL, BRAKING, DECEL, KMH_FACTOR
    MAX_SPEED = SEGMENT_LENGTH / (1 / FPS) * 0.9
    ACCEL = MAX_SPEED / 5.8
    BRAKING = -MAX_SPEED / 3.0
    DECEL = -MAX_SPEED / 8.5
    KMH_FACTOR = MAX_DISPLAY_KMH / max(1.0, MAX_SPEED)


def pick_auto_profile() -> str:
    cpu_count = os.cpu_count() or 2
    cpu_name = (os.environ.get("PROCESSOR_IDENTIFIER") or "").lower()

    if cpu_count <= 2 or "pentium" in cpu_name or "celeron" in cpu_name:
        return "ultra-low"
    if cpu_count <= 4:
        return "low"
    return "normal"


def apply_performance_profile(perf: str) -> str:
    global SCREEN_WIDTH, SCREEN_HEIGHT, FPS, DRAW_DISTANCE, CLOUD_LAYERS
    profile = pick_auto_profile() if perf == "auto" else perf

    if profile == "ultra-low":
        SCREEN_WIDTH, SCREEN_HEIGHT = 640, 360
        FPS = 40
        DRAW_DISTANCE = 72
        CLOUD_LAYERS = 0
    elif profile == "low":
        SCREEN_WIDTH, SCREEN_HEIGHT = 800, 450
        FPS = 45
        DRAW_DISTANCE = 100
        CLOUD_LAYERS = 1
    else:
        SCREEN_WIDTH, SCREEN_HEIGHT = 960, 540
        FPS = 60
        DRAW_DISTANCE = 160
        CLOUD_LAYERS = 3

    recalc_physics()
    return profile


def adapt_performance(current_profile: str, smoothed_dt: float) -> str:
    """Downgrade quality automatically if frame-time is too high for sustained periods."""
    global SCREEN_WIDTH, SCREEN_HEIGHT, FPS, DRAW_DISTANCE, CLOUD_LAYERS

    if smoothed_dt < 0.038:  # ~26+ fps sustained, no downgrade needed
        return current_profile

    idx = PERF_ORDER.index(current_profile)
    if idx == 0:
        # Already ultra-low; trim draw distance only.
        DRAW_DISTANCE = max(56, DRAW_DISTANCE - 4)
        return current_profile

    next_profile = PERF_ORDER[idx - 1]
    return apply_performance_profile(next_profile)


def build_track(progress_cb: Callable[[float], None] | None = None) -> list[Segment]:
    """Build exactly TRACK_LENGTH segments quickly.

    Note: cursor must advance monotonically (no modulo wrap) to avoid infinite
    loading loops on slower machines.
    """
    track: list[Segment] = [Segment(i) for i in range(TRACK_LENGTH)]

    def add_section(start: int, length: int, curve: float, hill: float) -> int:
        for i in range(length):
            idx = start + i
            p = i / max(1, length - 1)
            smooth = (1 - math.cos(p * math.pi)) / 2
            track[idx].curve = curve * smooth
            track[idx].y = hill * smooth
        return start + length

    cursor = 0

    while cursor < TRACK_LENGTH:
        for length, curve, hill in TRACK_PATTERN:
            if cursor >= TRACK_LENGTH:
                break
            real_len = min(length, TRACK_LENGTH - cursor)
            cursor = add_section(cursor, real_len, curve, hill)
            if progress_cb:
                progress_cb(cursor / TRACK_LENGTH)

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

    if CLOUD_LAYERS <= 0:
        return

    offset = int(pygame.time.get_ticks() * (0.02 + speed_percent * 0.05)) % SCREEN_WIDTH
    for i in range(-1, CLOUD_LAYERS + 1):
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

    wall_h1 = w1 * 0.14
    wall_h2 = w2 * 0.14
    left_wall = [(x1 - w1 * WALL_LIMIT, y1), (x1 - w1 * WALL_LIMIT, y1 - wall_h1), (x2 - w2 * WALL_LIMIT, y2 - wall_h2), (x2 - w2 * WALL_LIMIT, y2)]
    right_wall = [(x1 + w1 * WALL_LIMIT, y1), (x1 + w1 * WALL_LIMIT, y1 - wall_h1), (x2 + w2 * WALL_LIMIT, y2 - wall_h2), (x2 + w2 * WALL_LIMIT, y2)]
    pygame.draw.polygon(surface, (165, 165, 180), left_wall)
    pygame.draw.polygon(surface, (165, 165, 180), right_wall)

    # roadside scenery
    if int(y1) % 2 == 0:
        tree_h1 = w1 * 0.16
        tree_h2 = w2 * 0.16
        left_tree = [
            (x1 - w1 * 1.35, y1),
            (x1 - w1 * 1.30, y1 - tree_h1),
            (x2 - w2 * 1.30, y2 - tree_h2),
            (x2 - w2 * 1.35, y2),
        ]
        right_tree = [
            (x1 + w1 * 1.35, y1),
            (x1 + w1 * 1.30, y1 - tree_h1),
            (x2 + w2 * 1.30, y2 - tree_h2),
            (x2 + w2 * 1.35, y2),
        ]
        pygame.draw.polygon(surface, (44, 120, 44), left_tree)
        pygame.draw.polygon(surface, (44, 120, 44), right_tree)
    else:
        post_h1 = w1 * 0.11
        post_h2 = w2 * 0.11
        left_post = [
            (x1 - w1 * 1.18, y1),
            (x1 - w1 * 1.16, y1 - post_h1),
            (x2 - w2 * 1.16, y2 - post_h2),
            (x2 - w2 * 1.18, y2),
        ]
        right_post = [
            (x1 + w1 * 1.18, y1),
            (x1 + w1 * 1.16, y1 - post_h1),
            (x2 + w2 * 1.16, y2 - post_h2),
            (x2 + w2 * 1.18, y2),
        ]
        pygame.draw.polygon(surface, (220, 220, 120), left_post)
        pygame.draw.polygon(surface, (220, 220, 120), right_post)


def draw_player_car(surface: pygame.Surface, player: PlayerState, speed_percent: float, crashed: bool, x_offset: int = 0) -> None:
    base_y = SCREEN_HEIGHT - 72
    cx = SCREEN_WIDTH // 2 + int(player.x * SCREEN_WIDTH * 0.35) + x_offset
    cy = base_y + int(math.sin(pygame.time.get_ticks() * 0.02) * (2 + speed_percent * 5))

    if player.exploded:
        color = (255, 110, 20)
    elif crashed:
        color = (255, 180, 30)
    else:
        color = player.car_color

    # F1-like silhouette in local coordinates
    body = [(-10, 20), (-18, 4), (-16, -12), (-8, -22), (0, -30), (8, -22), (16, -12), (18, 4), (10, 20)]
    wing_front = [(-20, -20), (20, -20), (14, -14), (-14, -14)]
    wing_rear = [(-24, 18), (24, 18), (20, 24), (-20, 24)]
    cockpit = [(-6, -12), (6, -12), (4, 2), (-4, 2)]

    ang = -player.heading
    def transform(points):
        out=[]
        for x,y in points:
            v=pygame.Vector2(x,y).rotate(ang)
            out.append((cx+v.x, cy+v.y))
        return out

    pygame.draw.polygon(surface, (30, 30, 30), transform(wing_rear))
    pygame.draw.polygon(surface, (30, 30, 30), transform(wing_front))
    pygame.draw.polygon(surface, color, transform(body))
    pygame.draw.polygon(surface, (180, 220, 245), transform(cockpit))


def draw_remote_marker(surface: pygame.Surface, rel_z: float, rel_x: float, color: tuple[int, int, int]) -> None:
    if rel_z <= 0 or rel_z > DRAW_DISTANCE * SEGMENT_LENGTH:
        return
    scale = CAMERA_DEPTH / rel_z
    marker_x = int((1 + scale * (rel_x * ROAD_WIDTH)) * SCREEN_WIDTH / 2)
    marker_y = int((1 - scale * (-160)) * SCREEN_HEIGHT / 2)
    size = max(6, int(scale * 380))
    pygame.draw.rect(surface, color, pygame.Rect(marker_x - size // 2, marker_y - size, size, size), border_radius=3)


def wrap_distance(a: float, b: float) -> float:
    total = TRACK_LENGTH * SEGMENT_LENGTH
    d = (a - b) % total
    if d > total / 2:
        d -= total
    return d


def to_camera_space(wx: float, wy: float, wz: float, cam_x: float, cam_y: float, cam_z: float, cam_yaw_deg: float) -> tuple[float, float, float]:
    dx = wx - cam_x
    dy = wy - cam_y
    dz = wz - cam_z
    yaw = math.radians(cam_yaw_deg)
    cos_y = math.cos(yaw)
    sin_y = math.sin(yaw)
    cx = dx * cos_y - dz * sin_y
    cz = dx * sin_y + dz * cos_y
    return cx, dy, cz


def project_camera_point(cx: float, cy: float, cz: float) -> tuple[float, float] | None:
    if cz <= 8:
        return None
    scale = CAMERA_DEPTH / cz
    sx = (1 + scale * cx) * SCREEN_WIDTH / 2
    sy = (1 - scale * cy) * SCREEN_HEIGHT / 2
    return sx, sy


def draw_quad_3d(
    surface: pygame.Surface,
    points: list[tuple[float, float, float]],
    color: tuple[int, int, int],
    cam_x: float,
    cam_y: float,
    cam_z: float,
    cam_yaw: float,
) -> None:
    projected: list[tuple[float, float]] = []
    for wx, wy, wz in points:
        cx, cy, cz = to_camera_space(wx, wy, wz, cam_x, cam_y, cam_z, cam_yaw)
        p = project_camera_point(cx, cy, cz)
        if p is None:
            return
        projected.append(p)
    pygame.draw.polygon(surface, color, projected)


def handle_crash(player: PlayerState, now: float) -> str | None:
    if abs(player.x) <= WALL_LIMIT or player.out_of_action:
        return None

    speed_pct = player.speed / max(1.0, MAX_SPEED)
    player.x = max(-WALL_LIMIT, min(WALL_LIMIT, player.x))

    if speed_pct >= EXPLOSION_SPEED_THRESHOLD:
        player.speed = 0.0
        player.out_of_action = True
        player.exploded = True
        return "explode"

    player.speed = 0.0
    player.x_velocity = 0.0
    player.out_of_action = True
    player.exploded = False
    player.crashed_until = now + CRASH_COOLDOWN
    return "stall"


def update_player(
    player: PlayerState,
    dt: float,
    steer_left: bool,
    steer_right: bool,
    accelerate: bool,
    brake: bool,
    now: float,
    can_drive: bool,
    road_curve: float,
) -> str | None:
    if player.out_of_action:
        player.speed = 0.0
        player.x_velocity = 0.0
        return None

    accel = DECEL
    if can_drive:
        if accelerate:
            accel = ACCEL
        elif brake:
            accel = BRAKING

    if now < player.crashed_until:
        accel = min(accel, DECEL)

    speed_factor = player.speed / max(1.0, MAX_SPEED)
    rot_speed = 120 * dt * (0.25 + speed_factor)

    steer_input = 0.0
    if steer_left and not steer_right:
        steer_input = -1.0
    elif steer_right and not steer_left:
        steer_input = 1.0

    player.heading += steer_input * rot_speed

    # steering returns toward center for stability
    player.heading *= 0.93
    player.heading = max(-30.0, min(30.0, player.heading))

    # lateral model:
    # - driver steering force (from heading)
    # - mild curve-follow assist (same sign as curve direction)
    # - center spring to avoid one-side drift into barriers
    turn_force = math.sin(math.radians(player.heading)) * (0.70 + 0.95 * speed_factor)
    curve_follow = road_curve * (0.22 + 0.55 * speed_factor)
    center_pull = -player.x * 0.42

    player.x_velocity += (turn_force + curve_follow + center_pull) * dt
    player.x_velocity *= 0.84
    player.x += player.x_velocity * dt

    player.speed = max(0.0, min(MAX_SPEED, player.speed + accel * dt))
    crash_event = handle_crash(player, now)

    total = TRACK_LENGTH * SEGMENT_LENGTH
    prev = player.position
    player.position = (player.position + player.speed * dt) % total
    if player.position < prev and player.speed > 0:
        player.lap += 1

    return crash_event


def render_world(surface: pygame.Surface, track: list[Segment], camera_player: PlayerState, remote_player: PlayerState | None) -> None:
    """True 3D-ish world renderer using camera-space transforms + polygon projection."""
    draw_background(surface, camera_player.speed / max(1.0, MAX_SPEED))

    cam_x = camera_player.x * ROAD_WIDTH
    cam_y = CAMERA_HEIGHT
    cam_z = camera_player.position
    cam_yaw = camera_player.heading * 0.6

    base_segment = int(camera_player.position // SEGMENT_LENGTH) % TRACK_LENGTH
    road_half = ROAD_WIDTH * 0.5

    quads: list[tuple[float, tuple[int, int, int], list[tuple[float, float, float]]]] = []

    x_acc = 0.0
    dx = 0.0
    world_z0 = camera_player.position

    for n in range(min(DRAW_DISTANCE, 120)):
        idx_seg = (base_segment + n) % TRACK_LENGTH
        seg = track[idx_seg]
        seg2 = track[(idx_seg + 1) % TRACK_LENGTH]

        z0 = world_z0 + n * SEGMENT_LENGTH
        z1 = world_z0 + (n + 1) * SEGMENT_LENGTH

        x0 = x_acc
        x_acc += dx
        dx += seg.curve * 0.03 * ROAD_WIDTH * 0.2
        x1 = x_acc

        y0 = seg.y
        y1 = seg2.y

        dark = (idx_seg // 3) % 2 == 0
        road_col = ROAD_DARK_COLOR if dark else ROAD_LIGHT_COLOR
        rumble_col = (220, 50, 50) if dark else (245, 245, 245)
        wall_col = WALL_COLOR

        road_quad = [
            (x0 - road_half, y0, z0),
            (x0 + road_half, y0, z0),
            (x1 + road_half, y1, z1),
            (x1 - road_half, y1, z1),
        ]
        quads.append((z0, road_col, road_quad))

        r0 = road_half * 1.12
        r1 = road_half * 1.12
        left_rumble = [(x0 - r0, y0, z0), (x0 - road_half, y0, z0), (x1 - road_half, y1, z1), (x1 - r1, y1, z1)]
        right_rumble = [(x0 + road_half, y0, z0), (x0 + r0, y0, z0), (x1 + r1, y1, z1), (x1 + road_half, y1, z1)]
        quads.append((z0 + 0.1, rumble_col, left_rumble))
        quads.append((z0 + 0.1, rumble_col, right_rumble))

        wh = 320
        left_wall = [(x0 - road_half * 1.04, y0, z0), (x0 - road_half * 1.04, y0 - wh, z0), (x1 - road_half * 1.04, y1 - wh, z1), (x1 - road_half * 1.04, y1, z1)]
        right_wall = [(x0 + road_half * 1.04, y0, z0), (x0 + road_half * 1.04, y0 - wh, z0), (x1 + road_half * 1.04, y1 - wh, z1), (x1 + road_half * 1.04, y1, z1)]
        # bright faces + dark caps make barriers pop
        quads.append((z0 + 0.2, wall_col, left_wall))
        quads.append((z0 + 0.2, wall_col, right_wall))
        left_cap = [(x0 - road_half * 1.04, y0 - wh, z0), (x0 - road_half * 1.08, y0 - wh + 18, z0), (x1 - road_half * 1.08, y1 - wh + 18, z1), (x1 - road_half * 1.04, y1 - wh, z1)]
        right_cap = [(x0 + road_half * 1.04, y0 - wh, z0), (x0 + road_half * 1.08, y0 - wh + 18, z0), (x1 + road_half * 1.08, y1 - wh + 18, z1), (x1 + road_half * 1.04, y1 - wh, z1)]
        quads.append((z0 + 0.19, (120, 120, 135), left_cap))
        quads.append((z0 + 0.19, (120, 120, 135), right_cap))

        # scenery: tree trunks + foliage billboards
        if n % 4 == 0:
            s_off = road_half * 1.55
            trunk_h = 180
            trunk_w = 34
            crown_h = 320
            crown_w = 130

            left_trunk = [(x0 - s_off - trunk_w, y0, z0), (x0 - s_off - trunk_w, y0 - trunk_h, z0), (x1 - s_off - trunk_w, y1 - trunk_h, z1), (x1 - s_off - trunk_w, y1, z1)]
            right_trunk = [(x0 + s_off + trunk_w, y0, z0), (x0 + s_off + trunk_w, y0 - trunk_h, z0), (x1 + s_off + trunk_w, y1 - trunk_h, z1), (x1 + s_off + trunk_w, y1, z1)]
            left_crown = [(x0 - s_off - crown_w, y0 - trunk_h + 30, z0), (x0 - s_off - crown_w, y0 - crown_h, z0), (x1 - s_off - crown_w, y1 - crown_h, z1), (x1 - s_off - crown_w, y1 - trunk_h + 30, z1)]
            right_crown = [(x0 + s_off + crown_w, y0 - trunk_h + 30, z0), (x0 + s_off + crown_w, y0 - crown_h, z0), (x1 + s_off + crown_w, y1 - crown_h, z1), (x1 + s_off + crown_w, y1 - trunk_h + 30, z1)]
            quads.append((z0 + 0.31, TREE_TRUNK_COLOR, left_trunk))
            quads.append((z0 + 0.31, TREE_TRUNK_COLOR, right_trunk))
            quads.append((z0 + 0.30, TREE_CROWN_COLOR, left_crown))
            quads.append((z0 + 0.30, TREE_CROWN_COLOR, right_crown))

    quads.sort(key=lambda t: t[0], reverse=True)
    for _, color, poly in quads:
        draw_quad_3d(surface, poly, color, cam_x, cam_y, cam_z, cam_yaw)

    if remote_player:
        rel_z = wrap_distance(remote_player.position, camera_player.position)
        rel_world_z = cam_z + rel_z
        car_x = remote_player.x * ROAD_WIDTH
        car_y = -80
        car_w = 120
        car_h = 70
        car = [
            (car_x - car_w, car_y, rel_world_z),
            (car_x + car_w, car_y, rel_world_z),
            (car_x + car_w, car_y - car_h, rel_world_z),
            (car_x - car_w, car_y - car_h, rel_world_z),
        ]
        draw_quad_3d(surface, car, remote_player.car_color, cam_x, cam_y, cam_z, cam_yaw)


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
    p1 = PlayerState(name="P1", car_color=P1_COLOR, x=-0.2)
    p2 = PlayerState(name="P2", car_color=P2_COLOR, x=0.2)
    net = NetSession(mode, host, port)
    race = RaceState(enabled=race_enabled, countdown_end=time.perf_counter() + 2.5)
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


def show_loading_screen(screen: pygame.Surface, ui: LoadingUI, text: str, progress: float = 0.0, force: bool = False) -> None:
    progress = max(0.0, min(1.0, progress))
    percent = int(progress * 100)
    if not force and percent == ui.last_percent:
        return
    ui.last_percent = percent

    screen.fill((20, 20, 30))

    title = ui.font_title.render(text, True, (230, 230, 230))
    pct = ui.font_small.render(f"{percent:3d}%", True, (230, 230, 230))

    cx = screen.get_width() // 2
    cy = screen.get_height() // 2
    screen.blit(title, (cx - title.get_width() // 2, cy - 44))

    bar_w = min(460, screen.get_width() - 80)
    bar_h = 18
    bar_x = cx - bar_w // 2
    bar_y = cy
    pygame.draw.rect(screen, (60, 60, 80), pygame.Rect(bar_x, bar_y, bar_w, bar_h), border_radius=6)
    fill_w = max(2, int(bar_w * progress))
    pygame.draw.rect(screen, (120, 210, 140), pygame.Rect(bar_x, bar_y, fill_w, bar_h), border_radius=6)
    pygame.draw.rect(screen, (190, 190, 210), pygame.Rect(bar_x, bar_y, bar_w, bar_h), width=2, border_radius=6)

    screen.blit(pct, (cx - pct.get_width() // 2, bar_y + 26))
    pygame.display.flip()

    for event in pygame.event.get([pygame.QUIT]):
        if event.type == pygame.QUIT:
            pygame.quit()
            raise SystemExit(0)


def run(mode: str, host: str, port: int, race_enabled: bool, performance: str, mod_path: str | None) -> None:
    active_mod = load_mod(mod_path)
    profile = apply_performance_profile(performance)

    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("Thumb Drive Racer")
    clock = pygame.time.Clock()

    loading_ui = LoadingUI(
        font_title=pygame.font.SysFont("consolas", 22),
        font_small=pygame.font.SysFont("consolas", 17),
    )
    show_loading_screen(screen, loading_ui, "Loading track...", 0.0, force=True)
    track = build_track(progress_cb=lambda p: show_loading_screen(screen, loading_ui, "Loading track...", p))
    show_loading_screen(screen, loading_ui, "Loading complete", 1.0, force=True)

    font = pygame.font.SysFont("consolas", 17)
    big_font = pygame.font.SysFont("consolas", 32, bold=True)
    player1, player2, net, race = init_mode(mode, host, port, race_enabled)

    smoothed_dt = 1 / max(1, FPS)
    last_adapt = time.perf_counter()

    running = True
    while running:
        dt = min(0.04, clock.tick(FPS) / 1000)
        smoothed_dt = smoothed_dt * 0.92 + dt * 0.08
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
                    race_setting = race.enabled
                    net.close()
                    player1, player2, net, race = init_mode(mode, host, port, race_setting)
                elif event.key == pygame.K_t:
                    race.enabled = not race.enabled
                    player1, player2, net, race = init_mode(mode, host, port, race.enabled)
                elif event.key == pygame.K_F8:
                    profile = apply_performance_profile(cycle_perf(profile))

        keys = pygame.key.get_pressed()
        race_started = not race.enabled or now >= race.countdown_end
        can_drive = race_started and not race.finished

        seg1 = track[int(player1.position // SEGMENT_LENGTH) % TRACK_LENGTH]
        crash1_event = update_player(
            player1,
            dt,
            steer_left=keys[pygame.K_a] or keys[pygame.K_LEFT],
            steer_right=keys[pygame.K_d] or keys[pygame.K_RIGHT],
            accelerate=keys[pygame.K_w] or keys[pygame.K_UP],
            brake=keys[pygame.K_s] or keys[pygame.K_DOWN],
            now=now,
            can_drive=can_drive,
            road_curve=seg1.curve,
        )

        crash2_event: str | None = None
        if mode == "local":
            seg2 = track[int(player2.position // SEGMENT_LENGTH) % TRACK_LENGTH]
            crash2_event = update_player(
                player2,
                dt,
                steer_left=keys[pygame.K_j],
                steer_right=keys[pygame.K_l],
                accelerate=keys[pygame.K_i],
                brake=keys[pygame.K_k],
                now=now,
                can_drive=can_drive,
                road_curve=seg2.curve,
            )
        elif mode in {"online-host", "online-join"}:
            net.tick({"position": player1.position, "speed": player1.speed, "x": player1.x, "lap": float(player1.lap)})
            player2.position = net.last_remote["position"]
            player2.speed = net.last_remote["speed"]
            player2.x = net.last_remote["x"]
            player2.lap = int(net.last_remote["lap"])

        check_race_finish(race, player1, player2, mode)

        # Adaptive downgrade every ~2 seconds if frame-time stays poor.
        if now - last_adapt > 2.0:
            new_profile = adapt_performance(profile, smoothed_dt)
            if new_profile != profile:
                profile = new_profile
            last_adapt = now

        render_world(screen, track, player1, player2 if mode != "single" else None)
        draw_player_car(screen, player1, player1.speed / max(1.0, MAX_SPEED), now < player1.crashed_until)
        if mode == "local":
            draw_player_car(screen, player2, player2.speed / max(1.0, MAX_SPEED), now < player2.crashed_until, x_offset=140)

        hud_lines = [
            f"Mode: {mode_label(mode)} | Perf: {profile} | Mod: {active_mod}",
            f"P1 Speed: {int(player1.speed * KMH_FACTOR):03d} km/h  Lap: {player1.lap}/{RACE_LAPS if race.enabled else '-'}",
            "Race Mode: ON (T)" if race.enabled else "Race Mode: OFF (T)",
            "Switch mode: TAB / F1-F4",
        ]

        if mode == "local":
            hud_lines.append(f"P2 Speed: {int(player2.speed * KMH_FACTOR):03d} km/h  Lap: {player2.lap}/{RACE_LAPS if race.enabled else '-'}")
            hud_lines.append("P2: I/J/K/L")

        if mode in {"online-host", "online-join"}:
            hud_lines.append(f"Network: {'connected' if net.connected else 'waiting'} ({host}:{port})")

        if crash1_event == "explode" or crash2_event == "explode":
            hud_lines.append("BOOM! High-speed crash. Car destroyed. Press R to restart.")
        elif crash1_event == "stall" or crash2_event == "stall":
            hud_lines.append("Crash! Car stopped. Press R to restart.")

        if player1.out_of_action or (mode == "local" and player2.out_of_action):
            hud_lines.append("Restart required: press R")

        for i, line in enumerate(hud_lines):
            screen.blit(font.render(line, True, (255, 255, 255)), (12, 10 + i * 20))

        if race.enabled and not race.finished and now < race.countdown_end:
            countdown = max(1, int(math.ceil(race.countdown_end - now)))
            label = big_font.render(str(countdown), True, (255, 230, 80))
            screen.blit(label, (SCREEN_WIDTH // 2 - label.get_width() // 2, 70))
        elif race.enabled and race.finished:
            text = big_font.render(f"{race.winner} Wins! (R to restart)", True, (255, 230, 80))
            screen.blit(text, (SCREEN_WIDTH // 2 - text.get_width() // 2, 70))

        screen.blit(font.render("P1: W/S accel-brake, A/D or Left/Right rotate | stability steering assist enabled", True, (255, 255, 255)), (12, SCREEN_HEIGHT - 44))
        screen.blit(font.render("R restart | T race toggle | F8 perf", True, (255, 255, 255)), (12, SCREEN_HEIGHT - 24))
        pygame.display.flip()

    net.close()
    pygame.quit()
    sys.exit(0)


def cycle_perf(current: str) -> str:
    idx = PERF_ORDER.index(current)
    return PERF_ORDER[(idx + 1) % len(PERF_ORDER)]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Thumb Drive Racer")
    parser.add_argument("--mode", choices=MODE_ORDER, default="single", help="Initial game mode")
    parser.add_argument("--host", default="127.0.0.1", help="Host IP for online modes")
    parser.add_argument("--port", type=int, default=50555, help="UDP port for online modes")
    parser.add_argument("--race", action="store_true", help="Start with race mode enabled")
    parser.add_argument(
        "--performance",
        choices=["auto", "ultra-low", "low", "normal"],
        default="auto",
        help="Rendering profile (use ultra-low for Pentium / older i3)",
    )
    parser.add_argument("--mod", default=None, help="Path to a JSON mod file")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    try:
        run(args.mode, args.host, args.port, args.race, args.performance, args.mod)
    except Exception as exc:
        print(f"Fatal error: {exc}")
        raise
