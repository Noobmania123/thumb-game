import math
import random
import sys
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
CAMERA_DEPTH = 0.84  # lower = wider field of view
MAX_SPEED = SEGMENT_LENGTH / (1 / FPS) * 0.9
ACCEL = MAX_SPEED / 6
BREAKING = -MAX_SPEED / 3
DECEL = -MAX_SPEED / 8
OFFROAD_DECEL = -MAX_SPEED / 2
OFFROAD_LIMIT = MAX_SPEED / 4
TRACK_LENGTH = 1600


@dataclass
class Segment:
    index: int
    curve: float = 0.0
    y: float = 0.0


def build_track() -> list[Segment]:
    """Create a looping track made of straight and curved hills."""
    track: list[Segment] = [Segment(i) for i in range(TRACK_LENGTH)]

    def add_road(start: int, length: int, curve: float, hill: float) -> None:
        for i in range(length):
            idx = (start + i) % TRACK_LENGTH
            progress = i / max(1, length - 1)
            smooth = (1 - math.cos(progress * math.pi)) / 2
            track[idx].curve = curve * smooth
            track[idx].y = hill * smooth

    start = 0
    presets = [
        (220, 0.0, 0),
        (150, 0.8, 120),
        (160, -0.9, -150),
        (200, 0.4, 80),
        (180, -0.3, 0),
        (210, 1.0, 150),
        (220, 0.0, -40),
        (140, -0.7, 90),
    ]

    while start < TRACK_LENGTH:
        length, curve, hill = random.choice(presets)
        add_road(start, min(length, TRACK_LENGTH - start), curve, hill)
        start += length

    return track


def project(
    world_x: float,
    world_y: float,
    world_z: float,
    camera_x: float,
    camera_y: float,
    camera_z: float,
) -> tuple[float, float, float]:
    """Project 3D-ish world points to screen for pseudo-3D illusion."""
    dz = world_z - camera_z
    scale = CAMERA_DEPTH / dz if dz != 0 else 0.0001
    x = (1 + scale * (world_x - camera_x)) * SCREEN_WIDTH / 2
    y = (1 - scale * (world_y - camera_y)) * SCREEN_HEIGHT / 2
    w = scale * ROAD_WIDTH * SCREEN_WIDTH / 2
    return x, y, w


def draw_background(surface: pygame.Surface, speed_percent: float) -> None:
    horizon = SCREEN_HEIGHT * 0.45
    sky = pygame.Rect(0, 0, SCREEN_WIDTH, int(horizon))
    ground = pygame.Rect(0, int(horizon), SCREEN_WIDTH, SCREEN_HEIGHT - int(horizon))
    pygame.draw.rect(surface, (111, 180, 255), sky)
    pygame.draw.rect(surface, (90, 180, 80), ground)

    # fake moving cloud stripes for motion
    offset = int(pygame.time.get_ticks() * (0.02 + speed_percent * 0.06)) % SCREEN_WIDTH
    for i in range(-1, 4):
        x = i * 340 - offset
        pygame.draw.ellipse(surface, (220, 240, 255), pygame.Rect(x, 50, 220, 60))


def draw_segment(
    surface: pygame.Surface,
    x1: float,
    y1: float,
    w1: float,
    x2: float,
    y2: float,
    w2: float,
    color: tuple[int, int, int],
    rumble_color: tuple[int, int, int],
    lane_color: tuple[int, int, int],
) -> None:
    if y2 >= y1:
        return

    rumble1 = w1 * 1.15
    rumble2 = w2 * 1.15

    grass = [(0, y2), (SCREEN_WIDTH, y2), (SCREEN_WIDTH, y1), (0, y1)]
    pygame.draw.polygon(surface, (80, 160, 70), grass)

    left_rumble = [
        (x1 - rumble1, y1),
        (x1 - w1, y1),
        (x2 - w2, y2),
        (x2 - rumble2, y2),
    ]
    right_rumble = [
        (x1 + w1, y1),
        (x1 + rumble1, y1),
        (x2 + rumble2, y2),
        (x2 + w2, y2),
    ]
    pygame.draw.polygon(surface, rumble_color, left_rumble)
    pygame.draw.polygon(surface, rumble_color, right_rumble)

    road = [(x1 - w1, y1), (x1 + w1, y1), (x2 + w2, y2), (x2 - w2, y2)]
    pygame.draw.polygon(surface, color, road)

    lane_w1 = w1 * 0.03
    lane_w2 = w2 * 0.03
    lane_x1 = x1
    lane_x2 = x2
    lane = [
        (lane_x1 - lane_w1, y1),
        (lane_x1 + lane_w1, y1),
        (lane_x2 + lane_w2, y2),
        (lane_x2 - lane_w2, y2),
    ]
    pygame.draw.polygon(surface, lane_color, lane)


def draw_car(surface: pygame.Surface, player_x: float, speed_percent: float) -> None:
    base_y = SCREEN_HEIGHT - 80
    center_x = SCREEN_WIDTH // 2 + int(player_x * SCREEN_WIDTH * 0.35)
    bob = int(math.sin(pygame.time.get_ticks() * 0.02) * (2 + speed_percent * 6))
    car_color = (230, 40, 50)

    body = pygame.Rect(center_x - 34, base_y - 20 + bob, 68, 34)
    roof = pygame.Rect(center_x - 20, base_y - 38 + bob, 40, 18)
    wheel_l = pygame.Rect(center_x - 40, base_y + 6 + bob, 12, 16)
    wheel_r = pygame.Rect(center_x + 28, base_y + 6 + bob, 12, 16)

    pygame.draw.rect(surface, (20, 20, 20), wheel_l)
    pygame.draw.rect(surface, (20, 20, 20), wheel_r)
    pygame.draw.rect(surface, car_color, body, border_radius=5)
    pygame.draw.rect(surface, (200, 225, 245), roof, border_radius=4)


def run() -> None:
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("Thumb Drive Racer (Pseudo-3D)")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("consolas", 20)

    track = build_track()

    position = 0.0
    speed = 0.0
    player_x = 0.0

    running = True
    while running:
        dt = clock.tick(FPS) / 1000

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

        keys = pygame.key.get_pressed()
        accel = 0.0
        if keys[pygame.K_UP] or keys[pygame.K_w]:
            accel = ACCEL
        elif keys[pygame.K_DOWN] or keys[pygame.K_s]:
            accel = BREAKING
        else:
            accel = DECEL

        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            player_x -= 2.2 * dt * (speed / MAX_SPEED + 0.3)
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            player_x += 2.2 * dt * (speed / MAX_SPEED + 0.3)

        speed += accel * dt
        speed = max(0.0, min(speed, MAX_SPEED))

        if abs(player_x) > 1.0 and speed > OFFROAD_LIMIT:
            speed += OFFROAD_DECEL * dt

        position = (position + speed * dt) % (TRACK_LENGTH * SEGMENT_LENGTH)

        base_segment = int(position // SEGMENT_LENGTH) % TRACK_LENGTH
        speed_percent = speed / MAX_SPEED if MAX_SPEED else 0.0

        draw_background(screen, speed_percent)

        max_y = SCREEN_HEIGHT
        x = 0.0
        dx = 0.0

        for n in range(DRAW_DISTANCE):
            current_index = (base_segment + n) % TRACK_LENGTH
            seg = track[current_index]
            seg_next = track[(current_index + 1) % TRACK_LENGTH]

            z1 = n * SEGMENT_LENGTH
            z2 = (n + 1) * SEGMENT_LENGTH

            x1, y1, w1 = project(
                x,
                seg.y,
                z1,
                player_x * ROAD_WIDTH,
                CAMERA_HEIGHT,
                0,
            )
            x += dx
            dx += seg.curve * 0.03
            x2, y2, w2 = project(
                x,
                seg_next.y,
                z2,
                player_x * ROAD_WIDTH,
                CAMERA_HEIGHT,
                0,
            )

            if y2 >= max_y:
                continue
            max_y = y2

            dark = (current_index // 3) % 2 == 0
            road_col = (57, 57, 57) if dark else (66, 66, 66)
            rumble_col = (220, 40, 40) if dark else (240, 240, 240)
            lane_col = (240, 240, 160)
            draw_segment(screen, x1, y1, w1, x2, y2, w2, road_col, rumble_col, lane_col)

        draw_car(screen, player_x, speed_percent)

        speed_text = font.render(f"Speed: {int(speed * 0.15):03d} km/h", True, (255, 255, 255))
        hint_text = font.render("WASD / Arrows to drive", True, (255, 255, 255))
        screen.blit(speed_text, (20, 20))
        screen.blit(hint_text, (20, 50))

        pygame.display.flip()

    pygame.quit()
    sys.exit(0)


if __name__ == "__main__":
    run()
