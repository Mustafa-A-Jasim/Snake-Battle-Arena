
import json
import math
import os
import queue
import random
import socket
import sys
import threading
import time
from array import array

import pygame


# ============================================================
# Snake Battle Arena Game
# - Full screen
# - Host / Join on same LAN
# - Auto-discover available hosts on LAN
# - 2+ players supported
# - Large map with camera + minimap
# - Obstacles
# - Name entry, styled header, KPI cards
# - High scores stored locally
# - Eat sound / bonus sound
# - Bonus increases snake length by 5
# - Lives before final game over
# - Right-click game menu
# - Multiplayer match timer: 10 / 15 / 30 minutes
# - Final multiplayer results page with ranking and stats
# - Selectable lives: 5 / 10 / 15 / Unlimited
# - Hold Space for 3x speed boost
# ============================================================

pygame.init()
SOUND_ENABLED = True
try:
    pygame.mixer.init(frequency=44100, size=-16, channels=1)
except pygame.error:
    SOUND_ENABLED = False

info = pygame.display.Info()
SCREEN_W, SCREEN_H = info.current_w, info.current_h
screen = pygame.display.set_mode((SCREEN_W, SCREEN_H), pygame.FULLSCREEN)
pygame.display.set_caption("Snake Battle Arena")
clock = pygame.time.Clock()
FPS = 60

HEADER_H = 90
FOOTER_H = 34
CELL = 24
WORLD_W_CELLS = 120
WORLD_H_CELLS = 80
WORLD_W_PX = WORLD_W_CELLS * CELL
WORLD_H_PX = WORLD_H_CELLS * CELL
PLAY_W = SCREEN_W
PLAY_H = SCREEN_H - HEADER_H - FOOTER_H
MINIMAP_W = 240
MINIMAP_H = 160
SCORES_FILE = "snake_scores_lan.json"

DISCOVERY_PORT = 54545
GAME_PORT = 54546
BONUS_GROWTH = 5
BONUS_INTERVAL = 4
BONUS_LIFETIME = 10.0
MAX_PLAYERS = 8
DEFAULT_PLAYER_LIVES = 5
RESPAWN_INVULN_SECONDS = 2.0
MENU_W = 230
MENU_ITEM_H = 36
MATCH_DURATIONS = [3, 5, 10, 15]
LIFE_OPTIONS = [5, 10, 15, 0]  # 0 = unlimited
SPRINT_MULTIPLIER = 3.0

BG = (8, 14, 25)
BG2 = (15, 24, 39)
PANEL = (24, 35, 56)
PANEL2 = (40, 56, 86)
WHITE = (242, 247, 255)
DIM = (172, 189, 220)
GRID = (20, 32, 54)
ACCENT = (88, 175, 255)
ACCENT2 = (0, 215, 175)
GREEN = (83, 230, 126)
YELLOW = (255, 214, 102)
ORANGE = (255, 155, 88)
RED = (255, 99, 99)
GOLD = (255, 199, 52)
SHADOW = (4, 8, 14)
OBSTACLE = (110, 115, 130)
FOOD = (255, 84, 110)
BONUS = (255, 212, 64)
OVERLAY = (2, 4, 12)

PLAYER_COLORS = [
    (83, 230, 126),
    (88, 175, 255),
    (255, 155, 88),
    (192, 132, 252),
    (255, 214, 102),
    (255, 99, 99),
    (0, 215, 175),
    (255, 110, 199),
]

TITLE_FONT = pygame.font.SysFont("segoe ui", 26, bold=True)
FONT = pygame.font.SysFont("segoe ui", 18)
FONT_BOLD = pygame.font.SysFont("segoe ui", 18, bold=True)
SMALL = pygame.font.SysFont("segoe ui", 14)
BIG = pygame.font.SysFont("segoe ui", 46, bold=True)
MID = pygame.font.SysFont("segoe ui", 24, bold=True)
TABLE_HEADER = pygame.font.SysFont("segoe ui", 16, bold=True)


def draw_text(surface, text, font, color, x, y, center=False):
    img = font.render(text, True, color)
    rect = img.get_rect()
    if center:
        rect.center = (x, y)
    else:
        rect.topleft = (x, y)
    surface.blit(img, rect)
    return rect


def shadow_panel(surface, rect, offset=5):
    r = rect.copy()
    r.x += offset
    r.y += offset
    pygame.draw.rect(surface, SHADOW, r, border_radius=18)


def rounded_panel(surface, rect, fill, radius=16, border=None, border_width=0):
    pygame.draw.rect(surface, fill, rect, border_radius=radius)
    if border and border_width:
        pygame.draw.rect(surface, border, rect, width=border_width, border_radius=radius)


def blend_color(color, target, amount):
    amount = max(0.0, min(1.0, amount))
    return tuple(int(c + (t - c) * amount) for c, t in zip(color, target))


def lighten(color, amount):
    return blend_color(color, (255, 255, 255), amount)


def darken(color, amount):
    return blend_color(color, (0, 0, 0), amount)


def draw_iso_shadow(surface, rect, alpha=80, offset=(5, 5), scale=(1.1, 0.6)):
    sw = max(8, int(rect.w * scale[0]))
    sh = max(6, int(rect.h * scale[1]))
    shadow = pygame.Surface((sw, sh), pygame.SRCALPHA)
    pygame.draw.ellipse(shadow, (0, 0, 0, alpha), shadow.get_rect())
    x = rect.centerx - sw // 2 + offset[0]
    y = rect.bottom - sh // 2 + offset[1]
    surface.blit(shadow, (x, y))


def draw_3d_tile(surface, rect, color, height=4, radius=8, outline=None):
    base = rect.copy()
    top = rect.copy()
    top.y -= height
    pygame.draw.rect(surface, darken(color, 0.35), base, border_radius=radius)
    pygame.draw.rect(surface, color, top, border_radius=radius)
    pygame.draw.rect(surface, lighten(color, 0.22), top.inflate(-6, -6), border_radius=max(4, radius - 3))
    edge_color = outline if outline else darken(color, 0.45)
    pygame.draw.rect(surface, edge_color, top, width=2, border_radius=radius)


def draw_food_gem(surface, rect, color, bonus=False):
    draw_iso_shadow(surface, rect, alpha=75, offset=(4, 6), scale=(0.95, 0.55))
    orb = rect.copy()
    orb.y -= 5
    pygame.draw.ellipse(surface, darken(color, 0.30), orb.move(0, 4))
    pygame.draw.ellipse(surface, color, orb)
    pygame.draw.ellipse(surface, lighten(color, 0.28), orb.inflate(-6, -6))
    highlight = pygame.Rect(orb.x + 4, orb.y + 3, max(4, orb.w // 3), max(4, orb.h // 3))
    pygame.draw.ellipse(surface, WHITE, highlight)
    if bonus:
        ring = orb.inflate(4, 4)
        pygame.draw.ellipse(surface, WHITE, ring, 2)


def draw_snake_turn(surface, rect, color, current_cell, prev_cell=None, next_cell=None, height=4, outline=None):
    top = rect.copy()
    top.y -= height
    center = top.center
    radius = max(6, top.w // 2)
    pygame.draw.circle(surface, darken(color, 0.35), (center[0], center[1] + height), radius)
    pygame.draw.circle(surface, color, center, radius)
    pygame.draw.circle(surface, lighten(color, 0.22), (center[0] - 2, center[1] - 2), max(3, radius - 5))
    for neighbor in (prev_cell, next_cell):
        if not neighbor:
            continue
        dx = neighbor[0] - current_cell[0]
        dy = neighbor[1] - current_cell[1]
        if dx != 0:
            width = top.w // 2 + 2
            bridge = pygame.Rect(top.centerx - width if dx < 0 else top.centerx, top.y + 4, width, top.h - 8)
            pygame.draw.rect(surface, color, bridge, border_radius=8)
        elif dy != 0:
            height_rect = top.h // 2 + 2
            bridge = pygame.Rect(top.x + 4, top.centery - height_rect if dy < 0 else top.centery, top.w - 8, height_rect)
            pygame.draw.rect(surface, color, bridge, border_radius=8)
    edge_color = outline if outline else darken(color, 0.45)
    pygame.draw.circle(surface, edge_color, center, radius, 2)


def load_image_asset(filename):
    path = os.path.join(os.path.dirname(__file__), filename)
    try:
        return pygame.image.load(path).convert_alpha()
    except Exception:
        return None


def draw_bonus_sprite(surface, rect):
    if BONUS_IMAGE is None:
        draw_food_gem(surface, rect, BONUS, bonus=True)
        return
    draw_iso_shadow(surface, rect, alpha=80, offset=(4, 6), scale=(1.0, 0.55))
    size = max(rect.w, rect.h) + 8
    sprite = pygame.transform.smoothscale(BONUS_IMAGE, (size, size))
    sprite_rect = sprite.get_rect(center=(rect.centerx, rect.centery - 4))
    surface.blit(sprite, sprite_rect)


def make_tone(freq=720, duration_ms=90, volume=0.30):
    if not SOUND_ENABLED:
        return None
    sample_rate = 44100
    count = int(sample_rate * duration_ms / 1000)
    amplitude = int(32767 * volume)
    buf = array("h")
    for i in range(count):
        t = i / sample_rate
        buf.append(int(amplitude * math.sin(2 * math.pi * freq * t)))
    return pygame.mixer.Sound(buffer=buf.tobytes())


EAT_SOUND = make_tone(800, 80, 0.30)
BONUS_SOUND = make_tone(1000, 140, 0.35)
DEAD_SOUND = make_tone(210, 240, 0.28)
LEVEL_UP_SOUND = make_tone(1250, 180, 0.34)
WIN_SOUND = make_tone(1450, 260, 0.36)
COUNTDOWN_SOUND = make_tone(620, 90, 0.25)
LEVEL_UP_SOUND = make_tone(1320, 180, 0.32)
BONUS_IMAGE = None


def play_sound(sound):
    if SOUND_ENABLED and sound is not None:
        try:
            sound.play()
        except pygame.error:
            pass


def load_scores():
    if not os.path.exists(SCORES_FILE):
        return {}
    try:
        with open(SCORES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_scores(data):
    try:
        with open(SCORES_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def get_high_score(name):
    return int(load_scores().get(name.strip(), 0)) if name.strip() else 0


def update_high_score(name, score):
    name = name.strip()
    if not name:
        return
    data = load_scores()
    old = int(data.get(name, 0))
    if score > old:
        data[name] = score
        save_scores(data)


def json_send(sock, payload, addr=None):
    raw = json.dumps(payload).encode("utf-8")
    if addr is None:
        sock.sendall(raw + b"\n")
    else:
        sock.sendto(raw, addr)


def format_seconds(seconds):
    seconds = max(0, int(seconds))
    mins = seconds // 60
    secs = seconds % 60
    return f"{mins:02d}:{secs:02d}"


def format_lives(value):
    return "Unlimited" if value == 0 else str(value)


LEVELS = {
    1: {"name": "Level 1", "speed": 7, "label": "Low Speed"},
    2: {"name": "Level 2", "speed": 11, "label": "Medium Speed"},
    3: {"name": "Level 3", "speed": 15, "label": "High Speed"},
}
MULTIPLAYER_SPEED = LEVELS[1]["speed"]


class Button:
    def __init__(self, x, y, w, h, text, bg=PANEL2, fg=WHITE, border=ACCENT):
        self.rect = pygame.Rect(x, y, w, h)
        self.text = text
        self.bg = bg
        self.fg = fg
        self.border = border

    def draw(self, surface):
        hovered = self.rect.collidepoint(pygame.mouse.get_pos())
        fill = self.bg if not hovered else (58, 80, 116)
        shadow_panel(surface, self.rect, 4)
        rounded_panel(surface, self.rect, fill, 14, self.border, 2)
        draw_text(surface, self.text, FONT_BOLD, self.fg, self.rect.centerx, self.rect.centery, center=True)

    def hit(self, event):
        return event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.rect.collidepoint(event.pos)


class CheckBox:
    def __init__(self, x, y, text, checked=False):
        self.rect = pygame.Rect(x, y, 22, 22)
        self.text = text
        self.checked = checked
        self.enabled = True

    def draw(self, surface):
        border_color = ACCENT2 if self.enabled else (90, 100, 120)
        text_color = WHITE if self.enabled else (120, 130, 150)
        fill_color = PANEL if self.enabled else (35, 42, 55)
        rounded_panel(surface, self.rect, fill_color, 6, border_color, 2)

        if self.checked:
            tick_color = ACCENT2 if self.enabled else (140, 150, 165)
            pygame.draw.line(surface, tick_color, (self.rect.x + 4, self.rect.y + 12), (self.rect.x + 9, self.rect.y + 17), 3)
            pygame.draw.line(surface, tick_color, (self.rect.x + 9, self.rect.y + 17), (self.rect.x + 18, self.rect.y + 5), 3)

        draw_text(surface, self.text, SMALL, text_color, self.rect.right + 8, self.rect.y + 2)

    def handle(self, event):
        if not self.enabled:
            return False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            label_rect = pygame.Rect(self.rect.x, self.rect.y, 260, self.rect.h)
            if label_rect.collidepoint(event.pos):
                self.checked = not self.checked
                return True
        return False


class ContextMenu:
    def __init__(self):
        self.visible = False
        self.x = 0
        self.y = 0
        self.items = []

    def open(self, x, y, items):
        self.visible = True
        self.x = x
        self.y = y
        self.items = items

    def close(self):
        self.visible = False
        self.items = []

    def draw(self, surface):
        if not self.visible:
            return

        h = len(self.items) * MENU_ITEM_H + 10
        rect = pygame.Rect(self.x, self.y, MENU_W, h)
        if rect.right > SCREEN_W:
            rect.x = SCREEN_W - rect.w - 10
        if rect.bottom > SCREEN_H:
            rect.y = SCREEN_H - rect.h - 10

        shadow_panel(surface, rect, 5)
        rounded_panel(surface, rect, PANEL, 12, ACCENT, 2)

        for i, item in enumerate(self.items):
            item_rect = pygame.Rect(rect.x + 6, rect.y + 6 + i * MENU_ITEM_H, rect.w - 12, MENU_ITEM_H - 2)
            hovered = item_rect.collidepoint(pygame.mouse.get_pos())
            fill = PANEL2 if hovered else PANEL
            rounded_panel(surface, item_rect, fill, 8)
            draw_text(surface, item["label"], FONT, WHITE, item_rect.x + 12, item_rect.y + 9)

        self.x = rect.x
        self.y = rect.y

    def handle_click(self, event):
        if not self.visible or event.type != pygame.MOUSEBUTTONDOWN:
            return None

        rect = pygame.Rect(self.x, self.y, MENU_W, len(self.items) * MENU_ITEM_H + 10)
        if not rect.collidepoint(event.pos):
            self.close()
            return None

        for i, item in enumerate(self.items):
            item_rect = pygame.Rect(rect.x + 6, rect.y + 6 + i * MENU_ITEM_H, rect.w - 12, MENU_ITEM_H - 2)
            if item_rect.collidepoint(event.pos):
                self.close()
                return item["action"]
        return None


def draw_shared_minimap(state, camera_x, camera_y):
    x = SCREEN_W - MINIMAP_W - 18
    y = HEADER_H + 16
    outer = pygame.Rect(x, y, MINIMAP_W, MINIMAP_H)
    shadow_panel(screen, outer, 5)
    rounded_panel(screen, outer, PANEL, 14, ACCENT2, 2)
    draw_text(screen, "Map", FONT_BOLD, WHITE, x + 12, y + 8)

    inner = pygame.Rect(x + 10, y + 34, MINIMAP_W - 20, MINIMAP_H - 44)
    pygame.draw.rect(screen, BG, inner, border_radius=10)
    sx = inner.w / WORLD_W_CELLS
    sy = inner.h / WORLD_H_CELLS

    for ox, oy in state.get("obstacles", []):
        pygame.draw.rect(screen, OBSTACLE, (inner.x + ox * sx, inner.y + oy * sy, max(2, sx), max(2, sy)))

    food = state.get("food")
    if food:
        fx, fy = food
        pygame.draw.circle(screen, FOOD, (int(inner.x + fx * sx), int(inner.y + fy * sy)), 3)
    bonus = state.get("bonus_food")
    if bonus:
        bx, by = bonus
        if BONUS_IMAGE is not None:
            mini_size = 12
            sprite = pygame.transform.smoothscale(BONUS_IMAGE, (mini_size, mini_size))
            sprite_rect = sprite.get_rect(center=(int(inner.x + bx * sx), int(inner.y + by * sy)))
            screen.blit(sprite, sprite_rect)
        else:
            pygame.draw.circle(screen, BONUS, (int(inner.x + bx * sx), int(inner.y + by * sy)), 3)

    for pdata in state.get("players", []):
        snake = pdata.get("snake", [])
        if snake:
            hx, hy = snake[0]
            color = pdata.get("color", PLAYER_COLORS[0])
            pygame.draw.circle(screen, color, (int(inner.x + hx * sx), int(inner.y + hy * sy)), 4)

    view_rect = pygame.Rect(
        inner.x + (camera_x / WORLD_W_PX) * inner.w,
        inner.y + (camera_y / WORLD_H_PX) * inner.h,
        max(6, (PLAY_W / WORLD_W_PX) * inner.w),
        max(6, (PLAY_H / WORLD_H_PX) * inner.h),
    )
    pygame.draw.rect(screen, WHITE, view_rect, 1)


def draw_shared_world(state, me):
    screen.fill(BG)
    camera_x = 0
    camera_y = 0
    if me and me.get("snake"):
        hx, hy = me["snake"][0]
        hx_px = hx * CELL + CELL // 2
        hy_px = hy * CELL + CELL // 2
        camera_x = max(0, min(WORLD_W_PX - PLAY_W, hx_px - PLAY_W // 2))
        camera_y = max(0, min(WORLD_H_PX - PLAY_H, hy_px - PLAY_H // 2))

    play_rect = pygame.Rect(0, HEADER_H, PLAY_W, PLAY_H)
    pygame.draw.rect(screen, BG, play_rect)

    start_gx = int(camera_x // CELL) * CELL
    start_gy = int(camera_y // CELL) * CELL
    for x in range(start_gx, camera_x + PLAY_W + CELL, CELL):
        sx = x - camera_x
        pygame.draw.line(screen, GRID, (sx, HEADER_H), (sx, HEADER_H + PLAY_H), 1)
    for y in range(start_gy, camera_y + PLAY_H + CELL, CELL):
        sy = HEADER_H + (y - camera_y)
        pygame.draw.line(screen, GRID, (0, sy), (PLAY_W, sy), 1)

    for ox, oy in state.get("obstacles", []):
        rect = pygame.Rect(ox * CELL - camera_x + 1, HEADER_H + oy * CELL - camera_y + 1, CELL - 2, CELL - 2)
        if rect.right >= 0 and rect.left <= PLAY_W and rect.bottom >= HEADER_H and rect.top <= HEADER_H + PLAY_H:
            pygame.draw.rect(screen, OBSTACLE, rect, border_radius=5)

    food = state.get("food")
    if food:
        fx, fy = food
        rect = pygame.Rect(fx * CELL - camera_x + 3, HEADER_H + fy * CELL - camera_y + 3, CELL - 6, CELL - 6)
        pygame.draw.ellipse(screen, FOOD, rect)

    bonus = state.get("bonus_food")
    if bonus:
        bx, by = bonus
        rect = pygame.Rect(bx * CELL - camera_x + 2, HEADER_H + by * CELL - camera_y + 2, CELL - 4, CELL - 4)
        draw_bonus_sprite(screen, rect)
        label_rect = draw_text(screen, "+ Bonus", SMALL, BONUS, rect.centerx, rect.top - 28, center=True)
        pygame.draw.line(screen, BONUS, (label_rect.left + 4, label_rect.bottom + 1), (label_rect.right - 4, label_rect.bottom + 1), 1)

    for pdata in state.get("players", []):
        color = pdata.get("color", PLAYER_COLORS[0])
        snake = pdata.get("snake", [])
        alive = pdata.get("alive", True)
        invuln = pdata.get("respawn_until", 0) > time.time()
        for idx, (x, y) in enumerate(snake):
            rect = pygame.Rect(x * CELL - camera_x + 1, HEADER_H + y * CELL - camera_y + 1, CELL - 2, CELL - 2)
            if rect.right < 0 or rect.left > PLAY_W or rect.bottom < HEADER_H or rect.top > HEADER_H + PLAY_H:
                continue
            draw_color = color if idx > 0 else tuple(min(255, c + 40) for c in color)
            if not alive:
                draw_color = (90, 90, 90)
            pygame.draw.rect(screen, draw_color, rect, border_radius=6)
            if invuln and idx == 0:
                pygame.draw.rect(screen, WHITE, rect, 2, border_radius=6)

        if snake:
            hx, hy = snake[0]
            tx = hx * CELL - camera_x
            ty = HEADER_H + hy * CELL - camera_y - 20
            if 0 <= tx <= PLAY_W and HEADER_H <= ty + 20 <= HEADER_H + PLAY_H:
                draw_text(screen, pdata.get("name", "P"), SMALL, WHITE, tx, ty)

    draw_shared_minimap(state, camera_x, camera_y)

    footer_rect = pygame.Rect(0, SCREEN_H - FOOTER_H, SCREEN_W, FOOTER_H)
    pygame.draw.rect(screen, BG2, footer_rect)
    hint = "Arrow Keys: Move   |   Hold Space: 3x Speed   |   Hold TAB: Standings   |   Ping shown in header   |   ESC: Exit Game"
    draw_text(screen, hint, SMALL, DIM, 12, SCREEN_H - 24)


def draw_floating_texts(effects, camera_x, camera_y):
    now = time.time()
    for effect in effects[:]:
        age = now - effect["start_time"]
        if age >= effect["duration"]:
            effects.remove(effect)
            continue
        progress = age / effect["duration"]
        world_x = effect["cell"][0] * CELL + CELL // 2
        world_y = effect["cell"][1] * CELL + CELL // 2
        screen_x = world_x - camera_x
        screen_y = HEADER_H + world_y - camera_y - int(progress * 46)
        if -60 <= screen_x <= PLAY_W + 60 and HEADER_H - 60 <= screen_y <= HEADER_H + PLAY_H + 60:
            draw_text(screen, effect["text"], FONT_BOLD, effect["color"], screen_x, screen_y, center=True)


def draw_shared_header(player_name, level, high_score, state, me, ping_ms=None):
    header = pygame.Rect(0, 0, SCREEN_W, HEADER_H)
    pygame.draw.rect(screen, BG2, header)
    pygame.draw.line(screen, ACCENT, (0, HEADER_H - 1), (SCREEN_W, HEADER_H - 1), 2)
    draw_text(screen, "Snake Battle Arena", TITLE_FONT, WHITE, 18, 14)
    draw_text(screen, f"Player: {player_name}", SMALL, DIM, 20, 52)

    score = me.get("score", 0) if me else 0
    alive = me.get("alive", False) if me else False
    lives = me.get("lives", 0) if me else 0
    players_count = len(state.get("players", [])) if state else 0
    remaining_time = format_seconds(state.get("remaining_time", 0)) if state else "00:00"
    lives_text = "INF" if lives == 0 and state.get("lives_setting", DEFAULT_PLAYER_LIVES) == 0 else str(lives)
    display_level = level
    single_player_mode = players_count == 1 and state.get("remaining_time", 0) == 0
    if single_player_mode:
        display_level = 1 + (score // 20)
    kpis = [
        ("Score", str(score), ACCENT),
        ("High", str(max(high_score, score)), ACCENT2),
    ]
    if single_player_mode:
        kpis.append(("Current", f"Level {display_level}", YELLOW))
    kpis.extend([
        ("Lives", lives_text, GOLD),
        ("Time", remaining_time, ORANGE),
        ("Players", str(players_count), GREEN if alive else RED),
    ])
    if ping_ms is not None and players_count > 1:
        kpis.append(("Ping", f"{int(ping_ms)} ms", ACCENT))
    card_w = 112
    gap = 8
    total_w = len(kpis) * card_w + max(0, len(kpis) - 1) * gap
    start_x = max(190, SCREEN_W - total_w - 24)
    for i, (t, v, c) in enumerate(kpis):
        r = pygame.Rect(start_x + i * (card_w + gap), 18, card_w, 52)
        rounded_panel(screen, r, PANEL, 14, c, 2)
        draw_text(screen, t, SMALL, DIM, r.centerx, r.y + 14, center=True)
        draw_text(screen, v, SMALL, WHITE, r.centerx, r.y + 32, center=True)


def draw_overlay(text, subtext):
    overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
    overlay.fill((OVERLAY[0], OVERLAY[1], OVERLAY[2], 150))
    screen.blit(overlay, (0, 0))
    panel = pygame.Rect(SCREEN_W // 2 - 300, SCREEN_H // 2 - 110, 600, 190)
    shadow_panel(screen, panel, 6)
    rounded_panel(screen, panel, PANEL, 20, ACCENT, 2)
    draw_text(screen, text, BIG, WHITE, panel.centerx, panel.y + 60, center=True)
    draw_text(screen, subtext, FONT, DIM, panel.centerx, panel.y + 120, center=True)


class GameServer:
    def __init__(self, host_name, level, match_minutes=10, lives_setting=DEFAULT_PLAYER_LIVES, bot_count=0, bot_difficulty="Normal"):
        self.host_name = host_name
        self.level = 1
        self.match_minutes = match_minutes
        self.lives_setting = lives_setting
        self.bot_count = max(0, min(MAX_PLAYERS - 1, int(bot_count)))
        self.bot_difficulty = bot_difficulty if bot_difficulty in ("Easy", "Normal", "Hard") else "Normal"
        self.match_duration_seconds = match_minutes * 60
        self.level_speed = MULTIPLAYER_SPEED
        self.running = False
        self.lock = threading.Lock()
        self.clients = {}
        self.players = {}
        self.addr_to_pid = {}
        self.food = None
        self.bonus_food = None
        self.bonus_spawn_time = 0.0
        self.obstacles = set()
        self.next_pid = 1
        self.server_socket = None
        self.discovery_socket = None
        self.last_tick = time.time()
        self.match_start_time = time.time()
        self.match_over = False
        self.waiting_to_start = True
        self.countdown_start_time = None
        self.countdown_seconds = 3
        self.world_seed = random.randint(1000, 999999)
        random.seed(self.world_seed)
        self._generate_obstacles()
        self.obstacles_cache = list(self.obstacles)
        self.food = self._spawn_item()
        self.state_seq = 0
        self.map_revision = 1
        self.obstacles_dirty = True

    def _generate_obstacles(self):
        for _ in range(55):
            x = random.randint(5, WORLD_W_CELLS - 10)
            y = random.randint(5, WORLD_H_CELLS - 10)
            length = random.randint(3, 9)
            horizontal = random.choice([True, False])
            for i in range(length):
                ox = x + i if horizontal else x
                oy = y if horizontal else y + i
                if 0 <= ox < WORLD_W_CELLS and 0 <= oy < WORLD_H_CELLS:
                    self.obstacles.add((ox, oy))

    def _spawn_item(self):
        occupied = set(self.obstacles)
        for pdata in self.players.values():
            for cell in pdata["snake"]:
                occupied.add(tuple(cell))
        if self.food:
            occupied.add(tuple(self.food))
        if self.bonus_food:
            occupied.add(tuple(self.bonus_food))
        while True:
            pos = (random.randint(0, WORLD_W_CELLS - 1), random.randint(0, WORLD_H_CELLS - 1))
            if pos not in occupied:
                return pos

    def _spawn_player_position(self):
        while True:
            x = random.randint(5, WORLD_W_CELLS - 6)
            y = random.randint(5, WORLD_H_CELLS - 6)
            snake = [(x, y), (x - 1, y), (x - 2, y)]
            ok = True
            for cell in snake:
                if cell in self.obstacles:
                    ok = False
                    break
                for pdata in self.players.values():
                    if cell in [tuple(c) for c in pdata["snake"]]:
                        ok = False
                        break
                if not ok:
                    break
            if ok:
                return snake

    def add_player(self, name, is_bot=False):
        pid = self.next_pid
        self.next_pid += 1
        snake = self._spawn_player_position()
        color = PLAYER_COLORS[(pid - 1) % len(PLAYER_COLORS)]
        self.players[pid] = {
            "id": pid,
            "name": name,
            "snake": [[c[0], c[1]] for c in snake],
            "dir": [1, 0],
            "next_dir": [1, 0],
            "score": 0,
            "alive": True,
            "game_over": False,
            "lives": 0 if self.lives_setting == 0 else self.lives_setting,
            "deaths": 0,
            "color": color,
            "foods": 0,
            "grow": 0,
            "respawn_until": 0,
            "sprinting": False,
            "paused": False,
            "is_bot": is_bot,
            "bot_difficulty": self.bot_difficulty if is_bot else "",
        }
        return pid

    def add_device_players(self):
        for bot_index in range(self.bot_count):
            if len(self.players) >= MAX_PLAYERS - 1:
                break
            self.add_player(f"Device {bot_index + 1}", is_bot=True)

    def get_elapsed_time(self):
        return max(0, int(time.time() - self.match_start_time))

    def get_remaining_time(self):
        if self.waiting_to_start or self.countdown_start_time is not None:
            return self.match_duration_seconds
        return max(0, int(self.match_duration_seconds - self.get_elapsed_time()))

    def start_countdown(self):
        if not self.match_over and self.waiting_to_start and self.countdown_start_time is None:
            self.countdown_start_time = time.time()

    def get_countdown_value(self):
        if self.countdown_start_time is None:
            return 0
        return max(0, self.countdown_seconds - int(time.time() - self.countdown_start_time))

    def get_results(self):
        players = list(self.players.values())
        sorted_players = sorted(
            players,
            key=lambda p: (-p["score"], -(999999 if self.lives_setting == 0 else p["lives"]), p["deaths"], p["name"].lower())
        )
        results = []
        for idx, pdata in enumerate(sorted_players, start=1):
            lives_value = "∞" if self.lives_setting == 0 else pdata["lives"]
            results.append({
                "rank": idx,
                "name": pdata["name"],
                "score": pdata["score"],
                "lives": lives_value,
                "deaths": pdata["deaths"],
                "status": "Alive" if pdata["alive"] and not pdata.get("game_over", False) else "Dead",
                "color": pdata["color"],
                "is_bot": pdata.get("is_bot", False),
            })
        alive_count = sum(1 for p in players if p["alive"] and not p.get("game_over", False))
        dead_count = len(players) - alive_count
        winner = results[0]["name"] if results else "No winner"
        return {
            "winner": winner,
            "alive_count": alive_count,
            "dead_count": dead_count,
            "results": results,
        }

    def serialize_player_state(self, pdata):
        return {
            "id": pdata["id"],
            "name": pdata["name"],
            "snake": pdata["snake"],
            "score": pdata["score"],
            "alive": pdata["alive"],
            "game_over": pdata.get("game_over", False),
            "lives": pdata["lives"],
            "deaths": pdata["deaths"],
            "color": pdata["color"],
            "respawn_until": pdata.get("respawn_until", 0),
            "is_bot": pdata.get("is_bot", False),
            "bot_difficulty": pdata.get("bot_difficulty", ""),
        }

    def start(self):
        self.running = True
        self.match_over = False
        self.waiting_to_start = True
        self.countdown_start_time = None
        with self.lock:
            self.add_device_players()
        threading.Thread(target=self.discovery_loop, daemon=True).start()
        threading.Thread(target=self.accept_loop, daemon=True).start()
        threading.Thread(target=self.game_loop, daemon=True).start()

    def stop(self):
        self.running = False
        try:
            if self.server_socket:
                self.server_socket.close()
        except Exception:
            pass
        try:
            if self.discovery_socket:
                self.discovery_socket.close()
        except Exception:
            pass
        for sock in list(self.clients.values()):
            try:
                sock.close()
            except Exception:
                pass

    def discovery_loop(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.discovery_socket = s
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("", DISCOVERY_PORT))
        while self.running:
            try:
                data, addr = s.recvfrom(2048)
                msg = data.decode("utf-8", errors="ignore").strip()
                if msg == "SNAKE_DISCOVERY":
                    payload = {
                        "type": "DISCOVERY_REPLY",
                        "name": self.host_name,
                        "players": len(self.players),
                        "max_players": MAX_PLAYERS,
                        "port": GAME_PORT,
                        "match_minutes": self.match_minutes,
                        "lives_setting": self.lives_setting,
                    }
                    s.sendto(json.dumps(payload).encode("utf-8"), addr)
            except Exception:
                pass

    def accept_loop(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket = server
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            server.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except (AttributeError, OSError):
            pass
        server.bind(("", GAME_PORT))
        server.listen(MAX_PLAYERS)
        while self.running:
            try:
                client, addr = server.accept()
                try:
                    client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                except (AttributeError, OSError):
                    pass
                threading.Thread(target=self.client_loop, args=(client, addr), daemon=True).start()
            except Exception:
                pass

    def client_loop(self, client, addr):
        client_file = client.makefile("r", encoding="utf-8")
        pid = None
        msg = {}
        try:
            while self.running:
                line = client_file.readline()
                if not line:
                    break
                msg = json.loads(line.strip())
                mtype = msg.get("type")
                if mtype == "JOIN":
                    with self.lock:
                        if len(self.players) >= MAX_PLAYERS:
                            json_send(client, {"type": "JOIN_DENIED", "reason": "Server full"})
                            break
                        pid = self.add_player(msg.get("name", "Player"), is_bot=False)
                        self.clients[pid] = client
                        self.addr_to_pid[addr] = pid
                        json_send(client, {
                            "type": "JOIN_OK",
                            "player_id": pid,
                            "speed": self.level_speed,
                            "world": [WORLD_W_CELLS, WORLD_H_CELLS],
                            "match_minutes": self.match_minutes,
                            "lives_setting": self.lives_setting,
                            "obstacles": self.obstacles_cache,
                            "map_revision": self.map_revision,
                        })
                elif mtype == "INPUT" and pid is not None:
                    nd = msg.get("dir")
                    sprint = bool(msg.get("sprint", False))
                    paused = msg.get("paused")
                    with self.lock:
                        if pid in self.players and self.players[pid]["alive"] and not self.players[pid].get("game_over", False) and not self.match_over:
                            if isinstance(paused, bool):
                                self.players[pid]["paused"] = paused
                            self.players[pid]["sprinting"] = sprint and not self.players[pid].get("paused", False)
                            cur = self.players[pid]["dir"]
                            if nd in ([0, -1], [0, 1], [-1, 0], [1, 0]):
                                if not (cur[0] == -nd[0] and cur[1] == -nd[1]):
                                    self.players[pid]["next_dir"] = nd
                elif mtype == "PING":
                    json_send(client, {"type": "PONG", "token": msg.get("token")})
                elif mtype == "START_MATCH" and pid is not None:
                    with self.lock:
                        self.start_countdown()
                elif mtype == "QUIT":
                    break
        except Exception:
            pass
        finally:
            if pid is not None:
                with self.lock:
                    self.players.pop(pid, None)
                    self.clients.pop(pid, None)
                try:
                    update_high_score(msg.get("name", ""), msg.get("score", 0))
                except Exception:
                    pass
            try:
                client.close()
            except Exception:
                pass

    def kill_player(self, pid):
        pdata = self.players.get(pid)
        if not pdata or pdata.get("game_over", False):
            return

        pdata["deaths"] += 1
        if self.lives_setting != 0:
            pdata["lives"] -= 1
            if pdata["lives"] <= 0:
                pdata["alive"] = False
                pdata["game_over"] = True
                return

        new_snake = self._spawn_player_position()
        pdata["snake"] = [[c[0], c[1]] for c in new_snake]
        pdata["dir"] = [1, 0]
        pdata["next_dir"] = [1, 0]
        pdata["grow"] = 0
        pdata["alive"] = True
        pdata["respawn_until"] = time.time() + RESPAWN_INVULN_SECONDS
        pdata["sprinting"] = False
        pdata["paused"] = False

    def spawn_bonus_if_needed(self, pdata):
        if pdata["foods"] > 0 and pdata["foods"] % BONUS_INTERVAL == 0 and self.bonus_food is None:
            self.bonus_food = self._spawn_item()
            self.bonus_spawn_time = time.time()

    def is_safe_bot_direction(self, pid, pdata, direction):
        hx, hy = pdata["snake"][0]
        dx, dy = direction
        new_head = (hx + dx, hy + dy)
        if new_head[0] < 0 or new_head[0] >= WORLD_W_CELLS or new_head[1] < 0 or new_head[1] >= WORLD_H_CELLS:
            return False
        if new_head in self.obstacles:
            return False

        blocked = set()
        for opid, opdata in self.players.items():
            body = opdata["snake"]
            if opid == pid and pdata["grow"] == 0 and len(body) > 0:
                body = body[:-1]
            for cell in body:
                blocked.add(tuple(cell))
        return new_head not in blocked

    def update_bot_direction(self, pid, pdata):
        if not pdata["alive"] or pdata.get("game_over", False) or pdata.get("paused", False):
            return
        if not pdata.get("snake"):
            return

        target = self.food or self.bonus_food
        hx, hy = pdata["snake"][0]
        current_dir = tuple(pdata["dir"])
        directions = [(1, 0), (-1, 0), (0, 1), (0, -1)]
        candidates = []
        fallback_candidates = []
        avoid_bonus = self.food is not None and self.bonus_food is not None
        difficulty = pdata.get("bot_difficulty", "Normal")
        accuracy = {
            "Easy": 0.90,
            "Normal": 0.95,
            "Hard": 1.00,
        }.get(difficulty, 0.95)
        for direction in directions:
            if current_dir[0] == -direction[0] and current_dir[1] == -direction[1]:
                continue
            if not self.is_safe_bot_direction(pid, pdata, direction):
                continue
            nx = hx + direction[0]
            ny = hy + direction[1]
            distance = 0 if target is None else abs(target[0] - nx) + abs(target[1] - ny)
            candidate = (distance, random.random(), direction)
            if avoid_bonus and (nx, ny) == tuple(self.bonus_food):
                fallback_candidates.append(candidate)
            else:
                candidates.append(candidate)

        if not candidates:
            candidates = fallback_candidates
        if candidates:
            candidates.sort()
            best_index = 0
            if len(candidates) > 1 and random.random() > accuracy:
                best_index = random.randint(1, len(candidates) - 1)
            pdata["next_dir"] = list(candidates[best_index][2])

    def reset_match(self):
        with self.lock:
            self.food = None
            self.bonus_food = None
            self.bonus_spawn_time = 0
            self.obstacles = set()
            self._generate_obstacles()
            self.obstacles_cache = list(self.obstacles)
            self.map_revision += 1
            self.obstacles_dirty = True
            self.match_start_time = time.time()
            self.match_over = False
            self.waiting_to_start = True
            self.countdown_start_time = None

            for _, pdata in self.players.items():
                snake = self._spawn_player_position()
                pdata["snake"] = [[c[0], c[1]] for c in snake]
                pdata["dir"] = [1, 0]
                pdata["next_dir"] = [1, 0]
                pdata["score"] = 0
                pdata["alive"] = True
                pdata["game_over"] = False
                pdata["lives"] = 0 if self.lives_setting == 0 else self.lives_setting
                pdata["deaths"] = 0
                pdata["foods"] = 0
                pdata["grow"] = 0
                pdata["respawn_until"] = 0
                pdata["sprinting"] = False
                pdata["paused"] = False

            self.food = self._spawn_item()

    def update_player_step(self, pid, pdata):
        if not pdata["alive"] or pdata.get("game_over", False):
            return
        if pdata.get("paused", False):
            return

        pdata["dir"] = list(pdata["next_dir"])
        hx, hy = pdata["snake"][0]
        dx, dy = pdata["dir"]
        new_head = (hx + dx, hy + dy)
        invulnerable = time.time() < pdata.get("respawn_until", 0)

        if new_head[0] < 0 or new_head[0] >= WORLD_W_CELLS or new_head[1] < 0 or new_head[1] >= WORLD_H_CELLS:
            if not invulnerable:
                self.kill_player(pid)
            return

        if new_head in self.obstacles:
            if not invulnerable:
                self.kill_player(pid)
            return

        other_cells = set()
        for opid, opdata in self.players.items():
            body = opdata["snake"]
            if opid == pid and pdata["grow"] == 0 and len(body) > 0:
                body = body[:-1]
            for cell in body:
                other_cells.add(tuple(cell))
        if new_head in other_cells:
            if not invulnerable:
                self.kill_player(pid)
            return

        pdata["snake"].insert(0, [new_head[0], new_head[1]])

        if self.food and new_head == tuple(self.food):
            pdata["score"] += 1
            pdata["foods"] += 1
            pdata["grow"] += 1
            self.food = self._spawn_item()
            self.spawn_bonus_if_needed(pdata)
        elif self.bonus_food and new_head == tuple(self.bonus_food):
            pdata["score"] += 5
            pdata["grow"] += BONUS_GROWTH
            self.bonus_food = None
            self.bonus_spawn_time = 0
        else:
            if pdata["grow"] > 0:
                pdata["grow"] -= 1
            else:
                if pdata["snake"]:
                    pdata["snake"].pop()

    def game_loop(self):
        while self.running:
            now = time.time()
            base_interval = max(0.05, 1.0 / self.level_speed)
            if now - self.last_tick < base_interval:
                time.sleep(0.005)
                continue
            self.last_tick = now

            with self.lock:
                if self.countdown_start_time is not None and time.time() - self.countdown_start_time >= self.countdown_seconds:
                    self.waiting_to_start = False
                    self.countdown_start_time = None
                    self.match_start_time = time.time()

                if self.waiting_to_start or self.countdown_start_time is not None:
                    self.broadcast_state()
                    continue

                if not self.match_over and self.get_remaining_time() <= 0:
                    self.match_over = True

                if not self.match_over:
                    for pid, pdata in list(self.players.items()):
                        if pdata.get("is_bot", False):
                            self.update_bot_direction(pid, pdata)
                            pdata["sprinting"] = False
                        self.update_player_step(pid, pdata)
                        if pdata.get("sprinting", False) and pdata["alive"] and not pdata.get("game_over", False):
                            extra_steps = max(0, int(SPRINT_MULTIPLIER) - 1)
                            for _ in range(extra_steps):
                                self.update_player_step(pid, pdata)
                                if not pdata["alive"] or pdata.get("game_over", False):
                                    break

                    if self.bonus_food and time.time() - self.bonus_spawn_time > BONUS_LIFETIME:
                        self.bonus_food = None
                        self.bonus_spawn_time = 0

                self.broadcast_state()

    def broadcast_state(self):
        self.state_seq += 1
        results_payload = self.get_results()
        player_states = [self.serialize_player_state(pdata) for pdata in self.players.values()]
        payload = {
            "type": "STATE",
            "food": self.food,
            "bonus_food": self.bonus_food,
            "players": player_states,
            "speed": self.level_speed,
            "match_minutes": self.match_minutes,
            "lives_setting": self.lives_setting,
            "remaining_time": self.get_remaining_time(),
            "elapsed_time": self.get_elapsed_time(),
            "match_over": self.match_over,
            "lobby": self.waiting_to_start,
            "countdown": self.get_countdown_value(),
            "host_name": self.host_name,
            "bot_difficulty": self.bot_difficulty,
            "server_sent_at": time.time(),
            "state_seq": self.state_seq,
            "map_revision": self.map_revision,
            "results": results_payload,
        }
        if self.obstacles_dirty:
            payload["obstacles"] = self.obstacles_cache
        dead_clients = []
        for pid, sock in self.clients.items():
            try:
                json_send(sock, payload)
            except Exception:
                dead_clients.append(pid)
        for pid in dead_clients:
            self.clients.pop(pid, None)
            self.players.pop(pid, None)
        if self.obstacles_dirty:
            self.obstacles_dirty = False


class ServerDiscovery:
    def find_servers(self, timeout=1.6):
        results = []
        seen = set()
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.settimeout(timeout)
        try:
            s.sendto(b"SNAKE_DISCOVERY", ("<broadcast>", DISCOVERY_PORT))
            start = time.time()
            while time.time() - start < timeout:
                try:
                    data, addr = s.recvfrom(2048)
                    msg = json.loads(data.decode("utf-8"))
                    key = (addr[0], msg.get("port"))
                    if key not in seen:
                        seen.add(key)
                        results.append({
                            "ip": addr[0],
                            "port": msg.get("port", GAME_PORT),
                            "name": msg.get("name", "Host"),
                            "players": msg.get("players", 0),
                            "max_players": msg.get("max_players", MAX_PLAYERS),
                            "match_minutes": msg.get("match_minutes", 10),
                            "lives_setting": msg.get("lives_setting", DEFAULT_PLAYER_LIVES),
                        })
                except socket.timeout:
                    break
                except Exception:
                    pass
        finally:
            s.close()
        return results


class NetworkClient:
    def __init__(self, name, server_ip, server_port):
        self.name = name
        self.server_ip = server_ip
        self.server_port = server_port
        self.sock = None
        self.file = None
        self.connected = False
        self.running = False
        self.player_id = None
        self.latest_state = None
        self.event_queue = queue.Queue()
        self.sprint = False
        self.last_sent_dir = [1, 0]
        self.ping_ms = None
        self.last_ping_sent_at = 0.0
        self.pending_pings = {}
        self.last_state_received_at = 0.0
        self.last_state_seq = 0
        self.state_latency_ms = None
        self.cached_obstacles = []
        self.map_revision = 0

    def connect(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except (AttributeError, OSError):
            pass
        self.sock.settimeout(5)
        self.sock.connect((self.server_ip, self.server_port))
        self.sock.settimeout(None)
        self.file = self.sock.makefile("r", encoding="utf-8")
        self.connected = True
        self.running = True
        json_send(self.sock, {"type": "JOIN", "name": self.name})
        threading.Thread(target=self.listen_loop, daemon=True).start()

    def listen_loop(self):
        try:
            while self.running:
                line = self.file.readline()
                if not line:
                    break
                msg = json.loads(line.strip())
                if msg.get("type") == "JOIN_OK":
                    self.player_id = msg.get("player_id")
                    self.cached_obstacles = msg.get("obstacles", self.cached_obstacles)
                    self.map_revision = int(msg.get("map_revision", self.map_revision))
                elif msg.get("type") == "JOIN_DENIED":
                    self.event_queue.put(msg)
                elif msg.get("type") == "PONG":
                    token = msg.get("token")
                    sent_at = self.pending_pings.pop(token, None)
                    if sent_at is not None:
                        self.ping_ms = max(0, int((time.perf_counter() - sent_at) * 1000))
                elif msg.get("type") == "STATE":
                    seq = int(msg.get("state_seq", 0))
                    if seq >= self.last_state_seq:
                        self.last_state_seq = seq
                        self.last_state_received_at = time.time()
                        if "obstacles" in msg:
                            self.cached_obstacles = msg.get("obstacles", self.cached_obstacles)
                        msg["obstacles"] = self.cached_obstacles
                        self.map_revision = int(msg.get("map_revision", self.map_revision))
                        server_sent_at = msg.get("server_sent_at")
                        if isinstance(server_sent_at, (int, float)):
                            self.state_latency_ms = max(0, int((time.time() - server_sent_at) * 1000))
                        self.latest_state = msg
        except Exception:
            pass
        finally:
            self.connected = False
            self.running = False

    def send_input(self, direction=None, sprint=None):
        if not self.connected:
            return
        if direction is not None:
            self.last_sent_dir = direction
        if sprint is not None:
            self.sprint = sprint
        try:
            json_send(self.sock, {"type": "INPUT", "dir": self.last_sent_dir, "sprint": self.sprint})
        except Exception:
            self.connected = False

    def send_pause(self, paused):
        if not self.connected:
            return
        if paused:
            self.sprint = False
        try:
            json_send(self.sock, {"type": "INPUT", "dir": self.last_sent_dir, "sprint": self.sprint, "paused": bool(paused)})
        except Exception:
            self.connected = False

    def send_ping(self):
        if not self.connected:
            return
        now = time.perf_counter()
        if now - self.last_ping_sent_at < 1.0:
            return
        token = str(time.time_ns())
        self.pending_pings[token] = now
        self.last_ping_sent_at = now
        try:
            json_send(self.sock, {"type": "PING", "token": token})
        except Exception:
            self.pending_pings.pop(token, None)
            self.connected = False

    def send_start_match(self):
        if not self.connected:
            return
        try:
            json_send(self.sock, {"type": "START_MATCH"})
        except Exception:
            self.connected = False

    def close(self):
        self.running = False
        try:
            if self.sock:
                json_send(self.sock, {"type": "QUIT", "name": self.name})
        except Exception:
            pass
        try:
            if self.sock:
                self.sock.close()
        except Exception:
            pass


class StartScreen:
    def __init__(self, initial_name=""):
        panel_w = min(1120, SCREEN_W - 80)
        panel_h = min(840, SCREEN_H - 40)
        self.panel = pygame.Rect((SCREEN_W - panel_w) // 2, (SCREEN_H - panel_h) // 2, panel_w, panel_h)

        self.name = initial_name
        self.selected_level = 1
        self.selected_match_minutes = 5
        self.selected_lives = DEFAULT_PLAYER_LIVES
        self.active_name = True
        self.servers = []
        self.selected_server = 0
        self.discovery = ServerDiscovery()
        self.status_text = "Ready"
        self.current_tab = 0
        self.device_players_enabled = False
        self.device_players_text = "3"
        self.active_device_players = False
        self.selected_bot_difficulty = "Normal"

        px = self.panel.x
        py = self.panel.y
        pw = self.panel.w

        self.name_label_y = py + 214
        self.name_box = pygame.Rect(px + 72, py + 248, 500, 60)

        self.left_col_x = px + 58
        self.right_col_x = px + pw - 358
        self.columns_top = py + 344

        self.mode_box = pygame.Rect(self.left_col_x, self.columns_top, 650, 170)
        self.summary_box = pygame.Rect(self.left_col_x, py + 556, 650, 198)
        self.discovery_panel = pygame.Rect(self.right_col_x, self.columns_top - 180, 310, 190)
        self.server_list_rect = pygame.Rect(self.right_col_x, self.columns_top + 90, 310, 295)
        self.duration_box = pygame.Rect(self.left_col_x, self.columns_top, 650, 126)
        self.lives_box = pygame.Rect(self.left_col_x, py + 492, 650, 126)
        self.level_box = None

        self.mode_single_checkbox = CheckBox(self.mode_box.x + 18, self.mode_box.y + 64, "Single Player", checked=True)
        self.mode_multi_checkbox = CheckBox(self.mode_box.x + 250, self.mode_box.y + 64, "Multiplayer", checked=False)
        self.host_checkbox = CheckBox(self.mode_box.x + 18, self.mode_box.y + 110, "Server / Host Mode", checked=False)
        self.client_checkbox = CheckBox(self.mode_box.x + 286, self.mode_box.y + 110, "Client Mode", checked=True)
        self.device_players_checkbox = CheckBox(self.summary_box.x + 18, self.summary_box.y + 138, "Challenge device players", checked=False)
        self.device_players_box = pygame.Rect(self.summary_box.x + 284, self.summary_box.y + 128, 70, 44)
        self.bot_difficulty_buttons = {
            "Easy": Button(self.summary_box.x + 382, self.summary_box.y + 128, 72, 34, "Easy", border=GREEN),
            "Normal": Button(self.summary_box.x + 462, self.summary_box.y + 128, 86, 34, "Normal", border=ACCENT),
            "Hard": Button(self.summary_box.x + 556, self.summary_box.y + 128, 72, 34, "Hard", border=ORANGE),
        }

        self.discover_btn = Button(self.discovery_panel.x + 64, self.discovery_panel.y + 84, 172, 36, "Find Servers", border=ACCENT2)
        self.next_btn = Button(self.panel.right - 350, self.panel.bottom - 56, 132, 42, "Next", border=ACCENT)
        self.back_btn = Button(self.panel.right - 500, self.panel.bottom - 56, 132, 42, "Back", border=YELLOW)
        self.start_btn = Button(self.panel.right - 350, self.panel.bottom - 56, 132, 42, "Play", border=GREEN)
        self.exit_btn = Button(self.panel.right - 200, self.panel.bottom - 56, 132, 42, "Exit", border=RED)

        duration_start_x = self.duration_box.x + 20
        self.duration_buttons = {
            3: Button(duration_start_x, self.duration_box.y + 62, 122, 34, "3 Min", border=GREEN),
            5: Button(duration_start_x + 138, self.duration_box.y + 62, 122, 34, "5 Min", border=ACCENT),
            10: Button(duration_start_x + 276, self.duration_box.y + 62, 122, 34, "10 Min", border=ACCENT2),
            15: Button(duration_start_x + 414, self.duration_box.y + 62, 122, 34, "15 Min", border=GOLD),
        }

        lives_start_x = self.lives_box.x + 20
        self.lives_buttons = {
            5: Button(lives_start_x, self.lives_box.y + 62, 122, 34, "5 Lives", border=GREEN),
            10: Button(lives_start_x + 138, self.lives_box.y + 62, 122, 34, "10 Lives", border=YELLOW),
            15: Button(lives_start_x + 276, self.lives_box.y + 62, 122, 34, "15 Lives", border=ORANGE),
            0: Button(lives_start_x + 414, self.lives_box.y + 62, 146, 34, "Unlimited", border=ACCENT2),
        }

        self.sync_mode_boxes()

    def sync_mode_boxes(self):
        if self.mode_single_checkbox.checked:
            self.mode_multi_checkbox.checked = False
        elif self.mode_multi_checkbox.checked:
            self.mode_single_checkbox.checked = False
        else:
            self.mode_multi_checkbox.checked = True

        if self.mode_single_checkbox.checked:
            self.host_checkbox.checked = False
            self.client_checkbox.checked = False
            self.host_checkbox.enabled = False
            self.client_checkbox.enabled = False
        else:
            self.host_checkbox.enabled = True
            self.client_checkbox.enabled = True
            if not self.host_checkbox.checked and not self.client_checkbox.checked:
                self.client_checkbox.checked = True
            if self.host_checkbox.checked and self.client_checkbox.checked:
                self.host_checkbox.checked = False

        host_multiplayer = self.mode_multi_checkbox.checked and self.host_checkbox.checked
        self.device_players_checkbox.enabled = host_multiplayer
        if not host_multiplayer:
            self.device_players_checkbox.checked = False
            self.active_device_players = False

    def scan_servers(self):
        self.status_text = "Scanning LAN for servers..."
        self.servers = self.discovery.find_servers()
        if self.servers:
            self.selected_server = 0
            self.status_text = f"Found {len(self.servers)} server(s)"
        else:
            self.status_text = "No servers found"

    def get_device_players_count(self):
        if not (self.mode_multi_checkbox.checked and self.host_checkbox.checked and self.device_players_checkbox.checked):
            return 0
        try:
            return max(0, min(MAX_PLAYERS - 1, int(self.device_players_text or "0")))
        except ValueError:
            return 0

    def draw_info_lines(self, lines, x, y, line_gap=18, color=DIM):
        for idx, line in enumerate(lines):
            draw_text(screen, line, SMALL, color, x, y + idx * line_gap)

    def draw_section_heading(self, title, subtitle, rect, border_color):
        tag = pygame.Rect(rect.x + 14, rect.y - 14, min(220, rect.w - 28), 28)
        rounded_panel(screen, tag, BG2, 10, border_color, 1)
        draw_text(screen, title, SMALL, WHITE, tag.x + 12, tag.y + 6)
        if subtitle:
            draw_text(screen, subtitle, SMALL, DIM, rect.x + 14, rect.y + 24)

    def server_item_rects(self):
        rects = []
        item_y = self.server_list_rect.y + 92
        item_h = 89
        gap = 12
        max_items = min(4, len(self.servers))
        for idx in range(max_items):
            rects.append(pygame.Rect(self.server_list_rect.x + 14, item_y + idx * (item_h + gap), self.server_list_rect.w - 28, item_h))
        return rects

    def draw_step_tabs(self):
        labels = [("Step 1", "Player & Mode"), ("Step 2", "Match Setup")]
        start_x = self.panel.x + 70
        y = self.panel.y + 152
        for idx, (step, label) in enumerate(labels):
            rect = pygame.Rect(start_x + idx * 250, y, 220, 52)
            active = idx == self.current_tab
            fill = PANEL2 if active else PANEL
            border = ACCENT if active else (75, 92, 122)
            rounded_panel(screen, rect, fill, 14, border, 2)
            draw_text(screen, step, SMALL, ACCENT2 if active else DIM, rect.x + 16, rect.y + 10)
            draw_text(screen, label, FONT_BOLD, WHITE, rect.x + 16, rect.y + 26)

    def draw_top_shell(self):
        screen.fill(BG)
        for y in range(0, SCREEN_H, 32):
            pygame.draw.line(screen, GRID, (0, y), (SCREEN_W, y), 1)

        shadow_panel(screen, self.panel, 8)
        rounded_panel(screen, self.panel, BG2, 24, ACCENT, 2)
        draw_text(screen, "Snake Battle Arena", MID, WHITE, self.panel.centerx, self.panel.y + 50, center=True)
        draw_text(screen, "Set up the match in two quick steps, then jump straight into the game.", SMALL, DIM, self.panel.centerx, self.panel.y + 82, center=True)

        self.draw_step_tabs()

    def draw_page_one(self):
        draw_text(screen, "Player Name", SMALL, DIM, self.name_box.x, self.name_label_y)
        rounded_panel(screen, self.name_box, PANEL, 12, ACCENT2 if self.active_name else DIM, 2)
        shown = self.name if self.name else "Type your name here..."
        draw_text(screen, shown, FONT, WHITE if self.name else DIM, self.name_box.x + 16, self.name_box.y + 18)

        rounded_panel(screen, self.mode_box, PANEL, 16, ACCENT, 2)
        self.draw_section_heading("Game Mode", "Choose how this device will play.", self.mode_box, ACCENT)
        self.mode_single_checkbox.draw(screen)
        self.mode_multi_checkbox.draw(screen)
        self.host_checkbox.draw(screen)
        self.client_checkbox.draw(screen)
        if self.mode_single_checkbox.checked:
            self.draw_info_lines([
                "Single player runs only on this PC.",
                "Host and client options are disabled in this mode.",
            ], self.mode_box.x + 18, self.mode_box.y + 146, line_gap=22)
        else:
            self.draw_info_lines([
                "Host opens a game on this PC.",
                "Client joins another PC on the same LAN.",
            ], self.mode_box.x + 18, self.mode_box.y + 146, line_gap=22)

        rounded_panel(screen, self.summary_box, PANEL, 16, ACCENT2, 2)
        self.draw_section_heading("Quick Summary", "Your setup so far.", self.summary_box, ACCENT2)
        summary_lines = [
            f"Name: {self.name.strip() or 'Player'}",
            "Mode: Single Player" if self.mode_single_checkbox.checked else "Mode: Multiplayer",
            "Role: Local only" if self.mode_single_checkbox.checked else ("Role: Host" if self.host_checkbox.checked else "Role: Client"),
        ]
        self.draw_info_lines(summary_lines, self.summary_box.x + 18, self.summary_box.y + 62, line_gap=24, color=WHITE)

        self.device_players_checkbox.draw(screen)
        box_border = ACCENT2 if self.active_device_players else DIM
        box_fill = PANEL if self.device_players_checkbox.enabled else (35, 42, 55)
        rounded_panel(screen, self.device_players_box, box_fill, 10, box_border, 2)
        count_text = self.device_players_text if self.device_players_text else "0"
        count_color = WHITE if self.device_players_checkbox.enabled else (120, 130, 150)
        draw_text(screen, count_text, FONT_BOLD, count_color, self.device_players_box.centerx, self.device_players_box.centery, center=True)
        for difficulty, btn in self.bot_difficulty_buttons.items():
            btn.bg = (58, 82, 122) if self.selected_bot_difficulty == difficulty else PANEL2
            btn.draw(screen)
        draw_text(screen, "Host only: fill empty seats with computer rivals.", SMALL, DIM, self.summary_box.x + 18, self.summary_box.y + 176)

        hint_rect = pygame.Rect(self.right_col_x - 20, self.columns_top - 100, 360, 360)
        rounded_panel(screen, hint_rect, PANEL, 16, GOLD, 2)
        self.draw_section_heading("How It Works", "Quick guide for both game modes.", hint_rect, GOLD)
        draw_text(screen, "Single Player", FONT_BOLD, WHITE, hint_rect.x + 18, hint_rect.y + 64)
        self.draw_info_lines([
            "Play solo on this PC with automatic level progression.",
            "Choose your lives before starting the match.",
            "Use Arrow Keys to move and hold Space to sprint.",
            f"Bonus food gives {BONUS_GROWTH} extra growth and more score.",
        ], hint_rect.x + 18, hint_rect.y + 90, line_gap=20)

        draw_text(screen, "Multiplayer", FONT_BOLD, WHITE, hint_rect.x + 18, hint_rect.y + 188)
        self.draw_info_lines([
            "Host creates a LAN game, Client joins from another PC.",
            "Host can add Device players when the room needs rivals.",
            "Use Step 2 to discover servers and join a running match.",
            f"Matches support up to {MAX_PLAYERS} players on the same network.",
        ], hint_rect.x + 18, hint_rect.y + 214, line_gap=20)

        self.next_btn.draw(screen)
        self.exit_btn.draw(screen)

    def draw_page_two(self):
        rounded_panel(screen, self.duration_box, PANEL, 16, ACCENT, 2)
        self.draw_section_heading("Match Duration", "Select how long the multiplayer match will run.", self.duration_box, ACCENT)
        for minutes, btn in self.duration_buttons.items():
            btn.bg = (58, 82, 122) if self.selected_match_minutes == minutes else PANEL2
            btn.draw(screen)

        rounded_panel(screen, self.lives_box, PANEL, 16, GOLD, 2)
        self.draw_section_heading("Lives", "Choose starting lives for all players.", self.lives_box, GOLD)
        for lives, btn in self.lives_buttons.items():
            btn.bg = (58, 82, 122) if self.selected_lives == lives else PANEL2
            btn.draw(screen)

        rounded_panel(screen, self.discovery_panel, PANEL, 16, ACCENT2, 2)
        self.draw_section_heading("LAN Discovery", "Search for games on your local network.", self.discovery_panel, ACCENT2)
        if self.mode_multi_checkbox.checked and self.client_checkbox.checked:
            self.discover_btn.draw(screen)
            self.draw_info_lines([
                self.status_text,
                "Select one server from the list below.",
            ], self.discovery_panel.x + 14, self.discovery_panel.y + 138, line_gap=22)
        else:
            self.draw_info_lines([
                "Discovery is only used in Multiplayer Client mode.",
                "Single player and Host mode can start directly.",
            ], self.discovery_panel.x + 14, self.discovery_panel.y + 106, line_gap=22)

        rounded_panel(screen, self.server_list_rect, PANEL, 16, ACCENT2, 2)
        self.draw_section_heading("Available Servers", "Server name | IP | players | timer | lives", self.server_list_rect, ACCENT2)
        if not self.servers:
            self.draw_info_lines([
                "No discovered servers yet.",
                "Click Find Servers in client mode.",
            ], self.server_list_rect.x + 14, self.server_list_rect.y + 112, line_gap=22)
        else:
            for idx, item in enumerate(self.server_item_rects()):
                srv = self.servers[idx]
                fill = (74, 104, 144) if idx == self.selected_server else PANEL2
                border = ACCENT if idx == self.selected_server else None
                rounded_panel(screen, item, fill, 10, border, 2 if border else 0)
                draw_text(screen, srv["name"], FONT_BOLD, WHITE, item.x + 10, item.y + 7)
                line2 = f"{srv['ip']}  |  {srv['players']}/{srv['max_players']} players"
                line3 = f"{srv.get('match_minutes', 10)} min  |  {format_lives(srv.get('lives_setting', DEFAULT_PLAYER_LIVES))} lives"
                draw_text(screen, line2, SMALL, DIM, item.x + 10, item.y + 39)
                draw_text(screen, line3, SMALL, DIM, item.x + 10, item.y + 59)

        self.back_btn.draw(screen)
        self.start_btn.draw(screen)
        self.exit_btn.draw(screen)

    def draw(self):
        self.draw_top_shell()
        if self.current_tab == 0:
            self.draw_page_one()
        else:
            self.draw_page_two()
        pygame.display.flip()

    def run(self):
        while True:
            clock.tick(FPS)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return None

                if event.type == pygame.KEYDOWN and self.current_tab == 0 and self.active_device_players:
                    if event.key == pygame.K_BACKSPACE:
                        self.device_players_text = self.device_players_text[:-1]
                    elif event.key in (pygame.K_RETURN, pygame.K_TAB):
                        self.active_device_players = False
                    elif event.unicode.isdigit() and len(self.device_players_text) < 1:
                        self.device_players_text = event.unicode

                elif event.type == pygame.KEYDOWN and self.active_name and self.current_tab == 0:
                    if event.key == pygame.K_BACKSPACE:
                        self.name = self.name[:-1]
                    elif event.key == pygame.K_RETURN:
                        self.current_tab = 1
                    elif event.key != pygame.K_RETURN:
                        if len(self.name) < 18 and event.unicode.isprintable():
                            self.name += event.unicode

                if event.type == pygame.MOUSEBUTTONDOWN:
                    self.active_name = self.current_tab == 0 and self.name_box.collidepoint(event.pos)
                    self.active_device_players = (
                        self.current_tab == 0
                        and self.device_players_checkbox.enabled
                        and self.device_players_box.collidepoint(event.pos)
                    )

                    if self.exit_btn.hit(event):
                        return None

                    if self.current_tab == 0:
                        before_single = self.mode_single_checkbox.checked
                        before_multi = self.mode_multi_checkbox.checked
                        before_host = self.host_checkbox.checked
                        before_client = self.client_checkbox.checked

                        self.mode_single_checkbox.handle(event)
                        self.mode_multi_checkbox.handle(event)
                        self.host_checkbox.handle(event)
                        self.client_checkbox.handle(event)
                        self.device_players_checkbox.handle(event)

                        if self.mode_single_checkbox.checked != before_single and self.mode_single_checkbox.checked:
                            self.mode_multi_checkbox.checked = False
                        if self.mode_multi_checkbox.checked != before_multi and self.mode_multi_checkbox.checked:
                            self.mode_single_checkbox.checked = False
                        if self.host_checkbox.checked != before_host and self.host_checkbox.checked:
                            self.client_checkbox.checked = False
                        if self.client_checkbox.checked != before_client and self.client_checkbox.checked:
                            self.host_checkbox.checked = False

                        self.sync_mode_boxes()
                        if self.device_players_checkbox.checked:
                            self.device_players_text = str(self.get_device_players_count() or 1)
                        for difficulty, btn in self.bot_difficulty_buttons.items():
                            if btn.hit(event) and self.device_players_checkbox.enabled:
                                self.selected_bot_difficulty = difficulty
                                self.device_players_checkbox.checked = True
                                self.device_players_text = str(self.get_device_players_count() or 1)

                        if self.next_btn.hit(event):
                            self.current_tab = 1

                    else:
                        if self.back_btn.hit(event):
                            self.current_tab = 0

                        if self.mode_multi_checkbox.checked and self.client_checkbox.checked and self.discover_btn.hit(event):
                            self.scan_servers()

                        for minutes, btn in self.duration_buttons.items():
                            if btn.hit(event):
                                self.selected_match_minutes = minutes

                        for lives, btn in self.lives_buttons.items():
                            if btn.hit(event):
                                self.selected_lives = lives

                        if self.start_btn.hit(event):
                            pname = self.name.strip() or "Player"
                            selected_server = self.servers[self.selected_server] if self.servers else None
                            if selected_server and self.client_checkbox.checked:
                                self.selected_match_minutes = selected_server.get("match_minutes", self.selected_match_minutes)
                                self.selected_lives = selected_server.get("lives_setting", self.selected_lives)
                            return {
                                "name": pname,
                                "single_player": self.mode_single_checkbox.checked,
                                "multiplayer": self.mode_multi_checkbox.checked,
                                "host_server": self.host_checkbox.checked,
                                "client_mode": self.client_checkbox.checked,
                                "level": 1,
                                "match_minutes": self.selected_match_minutes,
                                "lives_setting": self.selected_lives,
                                "bot_count": self.get_device_players_count(),
                                "bot_difficulty": self.selected_bot_difficulty,
                                "server": selected_server,
                            }

                        if self.servers:
                            for idx, item in enumerate(self.server_item_rects()):
                                if item.collidepoint(event.pos):
                                    self.selected_server = idx

            self.draw()


class MultiplayerGame:
    def __init__(self, player_name, level, host_server=True, selected_server=None, match_minutes=10, lives_setting=DEFAULT_PLAYER_LIVES, bot_count=0, bot_difficulty="Normal"):
        self.player_name = player_name
        self.level = level
        self.host_server = host_server
        self.selected_server = selected_server
        self.match_minutes = match_minutes
        self.lives_setting = lives_setting
        self.bot_count = bot_count
        self.bot_difficulty = bot_difficulty
        self.local_high = get_high_score(player_name)
        self.server = None
        self.client = None
        self.running = True
        self.last_dir = [1, 0]
        self.last_food = None
        self.last_bonus = None
        self.context_menu = ContextMenu()
        self.paused = False
        self.return_to_main_menu = False
        self.sprint_held = False
        self.start_match_btn = Button(SCREEN_W // 2 - 95, SCREEN_H // 2 + 150, 190, 44, "Start Match", border=GREEN)
        self.last_countdown_value = None
        self.match_result_sound_played = False
        self.show_live_results = False
        self.floating_texts = []
        self.last_local_score = 0

    def start_network(self):
        target_ip = None
        target_port = GAME_PORT
        if self.host_server:
            self.level = 1
            self.server = GameServer(self.player_name, self.level, self.match_minutes, self.lives_setting, self.bot_count, self.bot_difficulty)
            self.server.start()
            target_ip = "127.0.0.1"
            time.sleep(0.25)
        elif self.selected_server:
            target_ip = self.selected_server["ip"]
            target_port = self.selected_server["port"]
            self.match_minutes = self.selected_server.get("match_minutes", self.match_minutes)
            self.lives_setting = self.selected_server.get("lives_setting", self.lives_setting)
        else:
            raise RuntimeError("No server selected")

        self.client = NetworkClient(self.player_name, target_ip, target_port)
        self.client.connect()
        start = time.time()
        while self.client.player_id is None and time.time() - start < 5:
            pygame.event.pump()
            time.sleep(0.02)
        if self.client.player_id is None:
            raise RuntimeError("Failed to join server")

    def close(self):
        if self.client:
            self.client.close()
        if self.server:
            self.server.stop()

    def find_me(self, state):
        pid = self.client.player_id if self.client else None
        if not state or not pid:
            return None
        for p in state.get("players", []):
            if p.get("id") == pid:
                return p
        return None

    def input_to_dir(self, event):
        if event.key == pygame.K_UP and self.last_dir != [0, 1]:
            return [0, -1]
        if event.key == pygame.K_DOWN and self.last_dir != [0, -1]:
            return [0, 1]
        if event.key == pygame.K_LEFT and self.last_dir != [1, 0]:
            return [-1, 0]
        if event.key == pygame.K_RIGHT and self.last_dir != [-1, 0]:
            return [1, 0]
        return None

    def handle_menu_action(self, action):
        if action == "pause":
            self.paused = not self.paused
            if self.client:
                self.client.send_pause(self.paused)
        elif action == "reset":
            if self.server:
                self.server.reset_match()
        elif action == "exit":
            self.return_to_main_menu = True
            self.running = False

    def draw_header(self, me, state):
        ping_ms = self.client.ping_ms if self.client else None
        if self.client and self.client.state_latency_ms is not None and ping_ms is not None:
            ping_ms = max(ping_ms, self.client.state_latency_ms)
        draw_shared_header(self.player_name, self.level, self.local_high, state, me, ping_ms=ping_ms)

    def draw_world(self, state, me):
        draw_shared_world(state, me)
        if me and me.get("snake"):
            hx, hy = me["snake"][0]
            hx_px = hx * CELL + CELL // 2
            hy_px = hy * CELL + CELL // 2
            camera_x = max(0, min(WORLD_W_PX - PLAY_W, hx_px - PLAY_W // 2))
            camera_y = max(0, min(WORLD_H_PX - PLAY_H, hy_px - PLAY_H // 2))
        else:
            camera_x = 0
            camera_y = 0
        draw_floating_texts(self.floating_texts, camera_x, camera_y)

    def draw_match_results(self, state, live_view=False):
        results = state.get("results", {})
        rows = results.get("results", [])
        winner = results.get("winner", "No winner")
        alive_count = results.get("alive_count", 0)
        dead_count = results.get("dead_count", 0)

        overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        overlay.fill((OVERLAY[0], OVERLAY[1], OVERLAY[2], 200))
        screen.blit(overlay, (0, 0))

        panel = pygame.Rect(SCREEN_W // 2 - 430, SCREEN_H // 2 - 250, 860, 500)
        shadow_panel(screen, panel, 8)
        rounded_panel(screen, panel, PANEL, 22, ACCENT, 2)

        title = "Live Standings" if live_view else "Match Finished"
        subtitle = f"Players: {len(rows)}   |   Alive Users: {alive_count}   |   Dead Users: {dead_count}" if live_view else f"Winner: {winner}"
        detail = "Hold TAB to view standings during the match." if live_view else f"Duration: {state.get('match_minutes', self.match_minutes)} min   |   Lives: {format_lives(state.get('lives_setting', self.lives_setting))}   |   Alive Users: {alive_count}   |   Dead Users: {dead_count}"
        draw_text(screen, title, BIG, WHITE, panel.centerx, panel.y + 48, center=True)
        draw_text(screen, subtitle, MID if not live_view else FONT_BOLD, GOLD if not live_view else WHITE, panel.centerx, panel.y + 98, center=True)
        draw_text(screen, detail, FONT, DIM, panel.centerx, panel.y + 130, center=True)

        table = pygame.Rect(panel.x + 40, panel.y + 160, panel.w - 80, 270)
        rounded_panel(screen, table, BG2, 16, ACCENT2, 2)

        headers = [("Rank", 60), ("Player", 220), ("Score", 120), ("Lives", 100), ("Deaths", 100), ("Status", 120)]
        x = table.x + 20
        y = table.y + 18
        for title, width in headers:
            draw_text(screen, title, TABLE_HEADER, WHITE, x, y)
            x += width

        pygame.draw.line(screen, ACCENT2, (table.x + 16, table.y + 44), (table.right - 16, table.y + 44), 1)

        row_y = table.y + 56
        for row in rows[:8]:
            color = tuple(row.get("color", WHITE))
            player_name = row["name"] + (" [BOT]" if row.get("is_bot") else "")
            rounded_panel(screen, pygame.Rect(table.x + 10, row_y - 4, table.w - 20, 28), PANEL, 8)
            draw_text(screen, str(row["rank"]), SMALL, WHITE, table.x + 22, row_y)
            draw_text(screen, player_name, SMALL, color, table.x + 82, row_y)
            draw_text(screen, str(row["score"]), SMALL, WHITE, table.x + 302, row_y)
            draw_text(screen, str(row["lives"]), SMALL, WHITE, table.x + 422, row_y)
            draw_text(screen, str(row["deaths"]), SMALL, WHITE, table.x + 522, row_y)
            draw_text(screen, row["status"], SMALL, WHITE, table.x + 622, row_y)
            row_y += 32

        footer = "Release TAB to hide standings." if live_view else "Right click for menu. Host can reset the match. ESC exits the game."
        draw_text(screen, footer, SMALL, DIM, panel.centerx, panel.bottom - 28, center=True)

    def draw_lobby(self, state):
        overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        overlay.fill((OVERLAY[0], OVERLAY[1], OVERLAY[2], 190))
        screen.blit(overlay, (0, 0))

        panel = pygame.Rect(SCREEN_W // 2 - 390, SCREEN_H // 2 - 270, 780, 520)
        shadow_panel(screen, panel, 8)
        rounded_panel(screen, panel, PANEL, 22, ACCENT, 2)

        countdown = state.get("countdown", 0)
        if countdown:
            draw_text(screen, str(countdown), BIG, GOLD, panel.centerx, panel.y + 90, center=True)
            draw_text(screen, "Get ready", MID, WHITE, panel.centerx, panel.y + 142, center=True)
            return

        players = state.get("players", [])
        bots = [p for p in players if p.get("is_bot")]
        humans = [p for p in players if not p.get("is_bot")]
        draw_text(screen, "Multiplayer Lobby", BIG, WHITE, panel.centerx, panel.y + 56, center=True)
        draw_text(screen, f"Host: {state.get('host_name', self.player_name)}   |   Timer: {state.get('match_minutes', self.match_minutes)} min   |   Lives: {format_lives(state.get('lives_setting', self.lives_setting))}", FONT, DIM, panel.centerx, panel.y + 104, center=True)

        left = pygame.Rect(panel.x + 42, panel.y + 140, 330, 240)
        right = pygame.Rect(panel.x + 408, panel.y + 140, 330, 240)
        rounded_panel(screen, left, BG2, 16, ACCENT2, 2)
        rounded_panel(screen, right, BG2, 16, GOLD, 2)
        draw_text(screen, f"LAN Players ({len(humans)})", FONT_BOLD, WHITE, left.x + 18, left.y + 18)
        draw_text(screen, f"Device Players ({len(bots)})", FONT_BOLD, WHITE, right.x + 18, right.y + 18)

        for idx, pdata in enumerate(humans[:6]):
            draw_text(screen, f"{idx + 1}. {pdata.get('name', 'Player')}", FONT, pdata.get("color", WHITE), left.x + 22, left.y + 56 + idx * 28)
        for idx, pdata in enumerate(bots[:6]):
            diff = pdata.get("bot_difficulty", state.get("bot_difficulty", "Normal"))
            draw_text(screen, f"{idx + 1}. {pdata.get('name', 'Device')} [BOT] - {diff}", SMALL, pdata.get("color", WHITE), right.x + 22, right.y + 58 + idx * 28)

        if self.host_server:
            self.start_match_btn.draw(screen)
            draw_text(screen, "Host: press Start Match when everybody is ready.", SMALL, DIM, panel.centerx, panel.bottom - 42, center=True)
        else:
            draw_text(screen, "Waiting for host to start the 3 second countdown...", FONT, DIM, panel.centerx, panel.bottom - 64, center=True)

    def draw_network_overlay(self, title, subtitle):
        overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        overlay.fill((OVERLAY[0], OVERLAY[1], OVERLAY[2], 135))
        screen.blit(overlay, (0, 0))
        panel = pygame.Rect(SCREEN_W // 2 - 280, SCREEN_H // 2 - 80, 560, 150)
        shadow_panel(screen, panel, 6)
        rounded_panel(screen, panel, PANEL, 18, ORANGE, 2)
        draw_text(screen, title, MID, WHITE, panel.centerx, panel.y + 46, center=True)
        draw_text(screen, subtitle, FONT, DIM, panel.centerx, panel.y + 92, center=True)

    def run(self):
        try:
            self.start_network()
        except Exception as e:
            screen.fill(BG)
            draw_text(screen, f"Connection failed: {e}", MID, WHITE, SCREEN_W // 2, SCREEN_H // 2, center=True)
            pygame.display.flip()
            time.sleep(2)
            return

        while self.running:
            clock.tick(FPS)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False

                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
                    items = [
                        {"label": "Pause Game" if not self.paused else "Resume Game", "action": "pause"},
                        {"label": "Reset Match (Host Only)", "action": "reset"},
                        {"label": "Exit Game", "action": "exit"},
                    ]
                    self.context_menu.open(event.pos[0], event.pos[1], items)

                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    action = self.context_menu.handle_click(event)
                    if action:
                        self.handle_menu_action(action)
                    elif self.host_server and self.client and self.client.latest_state and self.client.latest_state.get("lobby") and self.start_match_btn.hit(event):
                        self.client.send_start_match()

                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        if self.context_menu.visible:
                            self.context_menu.close()
                        else:
                            items = [
                                {"label": "Pause Game" if not self.paused else "Resume Game", "action": "pause"},
                                {"label": "Reset Match (Host Only)", "action": "reset"},
                                {"label": "Exit Game", "action": "exit"},
                            ]
                            self.context_menu.open(SCREEN_W // 2 - MENU_W // 2, SCREEN_H // 2 - 80, items)
                    elif event.key == pygame.K_TAB:
                        self.show_live_results = True
                    elif event.key == pygame.K_SPACE:
                        self.sprint_held = True
                        if self.client and not self.paused:
                            self.client.send_input(sprint=True)
                    elif not self.paused:
                        nd = self.input_to_dir(event)
                        if nd:
                            self.last_dir = nd
                            self.client.send_input(direction=nd)

                elif event.type == pygame.KEYUP:
                    if event.key == pygame.K_TAB:
                        self.show_live_results = False
                    elif event.key == pygame.K_SPACE:
                        self.sprint_held = False
                        if self.client:
                            self.client.send_input(sprint=False)

            state = self.client.latest_state
            if not state:
                screen.fill(BG)
                draw_text(screen, "Waiting for server state...", MID, WHITE, SCREEN_W // 2, SCREEN_H // 2, center=True)
                pygame.display.flip()
                continue
            stale_seconds = 0.0
            if self.client and self.client.last_state_received_at:
                stale_seconds = max(0.0, time.time() - self.client.last_state_received_at)

            me = self.find_me(state)
            score = me.get("score", 0) if me else 0
            if score > self.local_high:
                self.local_high = score
                update_high_score(self.player_name, score)
            if self.client:
                self.client.send_ping()

            current_food = tuple(state.get("food")) if state.get("food") else None
            current_bonus = tuple(state.get("bonus_food")) if state.get("bonus_food") else None
            if self.last_food is not None and current_food is not None and self.last_food != current_food:
                play_sound(EAT_SOUND)
                if me and me.get("snake") and score - self.last_local_score >= 1:
                    self.floating_texts.append({
                        "text": "+1 Point",
                        "cell": tuple(me["snake"][0]),
                        "color": FOOD,
                        "start_time": time.time(),
                        "duration": 0.9,
                    })
            if self.last_bonus is not None and self.last_bonus is not None and current_bonus is None:
                play_sound(BONUS_SOUND)
                if me and me.get("snake") and score - self.last_local_score >= 5:
                    self.floating_texts.append({
                        "text": "+5 Points",
                        "cell": tuple(me["snake"][0]),
                        "color": BONUS,
                        "start_time": time.time(),
                        "duration": 1.0,
                    })
            self.last_food = current_food
            self.last_bonus = current_bonus
            self.last_local_score = score

            self.draw_world(state, me)
            self.draw_header(me, state)

            countdown = state.get("countdown", 0)
            if countdown and countdown != self.last_countdown_value:
                play_sound(COUNTDOWN_SOUND)
            self.last_countdown_value = countdown

            if state.get("lobby", False) or countdown:
                self.draw_lobby(state)

            if self.paused and not state.get("match_over", False):
                draw_overlay("Paused", "Right click to resume, exit, or return to menu")

            if state.get("match_over", False):
                if not self.match_result_sound_played:
                    play_sound(WIN_SOUND)
                    self.match_result_sound_played = True
                self.draw_match_results(state)
            elif self.show_live_results and not state.get("lobby", False) and not countdown:
                self.draw_match_results(state, live_view=True)

            if stale_seconds >= 3.0:
                self.draw_network_overlay("Connection Unstable", "No new state received for a while. Keeping the last known frame on screen.")
            elif stale_seconds >= 0.8:
                latency_text = f"{int(stale_seconds * 1000)} ms since last update"
                self.draw_network_overlay("Network Slow", latency_text)

            self.context_menu.draw(screen)
            pygame.display.flip()

        self.close()


class LocalSinglePlayerGame:
    def __init__(self, player_name, level, lives_setting=DEFAULT_PLAYER_LIVES):
        self.player_name = player_name.strip() or "Player"
        self.base_level = level
        self.level = level
        self.base_speed = LEVELS[level]["speed"]
        self.speed = self.base_speed
        self.local_high = get_high_score(self.player_name)
        self.obstacles = set()
        self.max_lives = lives_setting
        self.context_menu = ContextMenu()
        self.paused = False
        self.return_to_main_menu = False
        self.sprint_held = False
        self.deaths = 0
        self.highest_level = level
        self.start_time = time.time()
        self.end_time = None
        self.game_over_buttons = []
        self.completed = False
        self.damage_flash_until = 0
        self.win_sound_played = False
        self.floating_texts = []
        self.generate_obstacles()
        self.reset()

    def generate_obstacles(self):
        self.obstacles = set()
        for _ in range(45):
            x = random.randint(5, WORLD_W_CELLS - 10)
            y = random.randint(5, WORLD_H_CELLS - 10)
            length = random.randint(3, 8)
            horizontal = random.choice([True, False])
            for i in range(length):
                ox = x + i if horizontal else x
                oy = y if horizontal else y + i
                if 0 <= ox < WORLD_W_CELLS and 0 <= oy < WORLD_H_CELLS:
                    self.obstacles.add((ox, oy))

    def spawn_item(self):
        occupied = set(self.obstacles)
        for c in self.snake:
            occupied.add(tuple(c))
        if self.food:
            occupied.add(tuple(self.food))
        if self.bonus_food:
            occupied.add(tuple(self.bonus_food))
        while True:
            pos = (random.randint(0, WORLD_W_CELLS - 1), random.randint(0, WORLD_H_CELLS - 1))
            if pos not in occupied:
                return pos

    def reset(self):
        x = WORLD_W_CELLS // 2
        y = WORLD_H_CELLS // 2
        self.snake = [[x, y], [x - 1, y], [x - 2, y]]
        self.direction = [1, 0]
        self.next_direction = [1, 0]
        self.score = 0
        self.foods = 0
        self.grow = 0
        self.food = None
        self.bonus_food = None
        self.bonus_spawn_time = 0
        self.running = True
        self.alive = True
        self.lives = self.max_lives
        self.level = self.base_level
        self.speed = self.base_speed
        self.deaths = 0
        self.highest_level = self.base_level
        self.start_time = time.time()
        self.end_time = None
        self.completed = False
        self.damage_flash_until = 0
        self.win_sound_played = False
        self.floating_texts = []
        self.food = self.spawn_item()
        self.last_tick = time.time()

    def soft_respawn(self):
        x = WORLD_W_CELLS // 2
        y = WORLD_H_CELLS // 2
        self.snake = [[x, y], [x - 1, y], [x - 2, y]]
        self.direction = [1, 0]
        self.next_direction = [1, 0]
        self.grow = 0

    def lose_life(self):
        if self.max_lives != 0:
            self.lives -= 1
        self.deaths += 1
        self.damage_flash_until = time.time() + 0.35
        play_sound(DEAD_SOUND)
        if self.max_lives != 0 and self.lives <= 0:
            self.alive = False
            self.end_time = time.time()
            update_high_score(self.player_name, self.score)
            return
        self.soft_respawn()

    def update_progression(self):
        new_level = min(5, 1 + (self.score // 20))
        if new_level > self.level:
            play_sound(LEVEL_UP_SOUND)
        self.level = new_level
        self.highest_level = max(self.highest_level, self.level)
        self.speed = self.base_speed + (self.level - 1)
        if self.score >= 80 and not self.completed:
            self.completed = True
            self.alive = False
            self.end_time = time.time()
            play_sound(WIN_SOUND)
            self.win_sound_played = True
            update_high_score(self.player_name, self.score)

    def update_step(self):
        if not self.alive or self.completed:
            return
        self.direction = list(self.next_direction)
        hx, hy = self.snake[0]
        dx, dy = self.direction
        new_head = [hx + dx, hy + dy]

        if new_head[0] < 0 or new_head[0] >= WORLD_W_CELLS or new_head[1] < 0 or new_head[1] >= WORLD_H_CELLS:
            self.lose_life()
            return
        if tuple(new_head) in self.obstacles:
            self.lose_life()
            return
        body = self.snake[:-1] if self.grow == 0 else self.snake
        if new_head in body:
            self.lose_life()
            return

        self.snake.insert(0, new_head)
        if self.food and tuple(new_head) == tuple(self.food):
            self.score += 1
            self.foods += 1
            self.grow += 1
            self.food = self.spawn_item()
            play_sound(EAT_SOUND)
            self.floating_texts.append({
                "text": "+1 Point",
                "cell": tuple(new_head),
                "color": FOOD,
                "start_time": time.time(),
                "duration": 0.9,
            })
            if self.foods > 0 and self.foods % BONUS_INTERVAL == 0 and self.bonus_food is None:
                self.bonus_food = self.spawn_item()
                self.bonus_spawn_time = time.time()
        elif self.bonus_food and tuple(new_head) == tuple(self.bonus_food):
            self.score += 5
            self.grow += BONUS_GROWTH
            self.bonus_food = None
            self.bonus_spawn_time = 0
            play_sound(BONUS_SOUND)
            self.floating_texts.append({
                "text": "+5 Points",
                "cell": tuple(new_head),
                "color": BONUS,
                "start_time": time.time(),
                "duration": 1.0,
            })
        else:
            if self.grow > 0:
                self.grow -= 1
            else:
                self.snake.pop()

        if self.bonus_food and time.time() - self.bonus_spawn_time > BONUS_LIFETIME:
            self.bonus_food = None
            self.bonus_spawn_time = 0
        self.update_progression()
        if self.score > self.local_high:
            self.local_high = self.score
            update_high_score(self.player_name, self.score)

    def handle_menu_action(self, action):
        if action == "pause":
            self.paused = not self.paused
        elif action == "reset":
            self.generate_obstacles()
            self.reset()
        elif action == "exit":
            self.return_to_main_menu = True
            self.running = False

    def draw(self):
        current_level = min(5, 1 + (self.score // 20))
        self.level = current_level
        self.highest_level = max(self.highest_level, current_level)
        state = {
            "food": self.food,
            "bonus_food": self.bonus_food,
            "obstacles": list(self.obstacles),
            "players": [{
                "id": 1,
                "name": self.player_name,
                "snake": self.snake,
                "score": self.score,
                "alive": self.alive,
                "game_over": not self.alive,
                "lives": self.lives,
                "respawn_until": 0,
                "color": PLAYER_COLORS[0],
            }],
            "remaining_time": 0,
            "lives_setting": self.max_lives,
        }
        me = state["players"][0]
        draw_shared_world(state, me)
        draw_shared_header(self.player_name, current_level, self.local_high, state, me)
        hx, hy = self.snake[0]
        hx_px = hx * CELL + CELL // 2
        hy_px = hy * CELL + CELL // 2
        camera_x = max(0, min(WORLD_W_PX - PLAY_W, hx_px - PLAY_W // 2))
        camera_y = max(0, min(WORLD_H_PX - PLAY_H, hy_px - PLAY_H // 2))
        draw_floating_texts(self.floating_texts, camera_x, camera_y)
        if time.time() < self.damage_flash_until:
            flash = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
            flash.fill((RED[0], RED[1], RED[2], 55))
            screen.blit(flash, (0, 0))

        if not self.alive:
            self.draw_game_over_panel()
        elif self.paused:
            draw_overlay("Paused", "Right click for menu options")

        self.context_menu.draw(screen)
        pygame.display.flip()

    def get_run_stats(self):
        end_time = self.end_time if self.end_time is not None else time.time()
        return {
            "score": self.score,
            "high_score": max(self.local_high, self.score),
            "level": self.level,
            "highest_level": self.highest_level,
            "speed": self.speed,
            "foods": self.foods,
            "deaths": self.deaths,
            "time": format_seconds(end_time - self.start_time),
            "completed": self.completed,
        }

    def draw_game_over_panel(self):
        stats = self.get_run_stats()
        overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        overlay.fill((OVERLAY[0], OVERLAY[1], OVERLAY[2], 210))
        screen.blit(overlay, (0, 0))

        panel = pygame.Rect(SCREEN_W // 2 - 390, SCREEN_H // 2 - 250, 780, 500)
        shadow_panel(screen, panel, 8)
        rounded_panel(screen, panel, PANEL, 22, ACCENT, 2)
        draw_text(screen, "Single Player Results", BIG, WHITE, panel.centerx, panel.y + 56, center=True)
        subtitle = "You finished all 5 levels. Choose what to do next." if stats.get("completed") else "No lives left. Choose what to do next."
        draw_text(screen, subtitle, FONT, DIM, panel.centerx, panel.y + 104, center=True)

        table = pygame.Rect(panel.x + 46, panel.y + 140, panel.w - 92, 228)
        rounded_panel(screen, table, BG2, 16, ACCENT2, 2)

        stats_lines = [
            ("Score", str(stats["score"]), ACCENT),
            ("High Score", str(stats["high_score"]), ACCENT2),
            ("Level", str(stats["level"]), YELLOW),
            ("Top Level", str(stats["highest_level"]), GOLD),
            ("Speed", f"{stats['speed']}x", ORANGE),
            ("Foods", str(stats["foods"]), GREEN),
            ("Deaths", str(stats["deaths"]), RED),
            ("Time", stats["time"], WHITE),
        ]

        col_x = table.x + 26
        col_y = table.y + 28
        for idx, (label, value, color) in enumerate(stats_lines):
            card = pygame.Rect(col_x + (idx % 2) * 320, col_y + (idx // 2) * 46, 292, 34)
            rounded_panel(screen, card, PANEL, 10)
            draw_text(screen, label, SMALL, DIM, card.x + 12, card.y + 9)
            draw_text(screen, value, SMALL, color, card.right - 14, card.y + 9, center=False)

        btn_y = panel.bottom - 88
        self.game_over_buttons = [
            ("play_again", Button(panel.x + 62, btn_y, 180, 42, "Play Again", border=GREEN)),
            ("exit", Button(panel.x + 300, btn_y, 180, 42, "Exit Game", border=RED)),
        ]
        for _, btn in self.game_over_buttons:
            btn.draw(screen)

    def run(self):
        while self.running:
            clock.tick(FPS)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False

                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
                    items = [
                        {"label": "Pause Game" if not self.paused else "Resume Game", "action": "pause"},
                        {"label": "Reset Game", "action": "reset"},
                        {"label": "Exit Game", "action": "exit"},
                    ]
                    self.context_menu.open(event.pos[0], event.pos[1], items)

                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if not self.alive:
                        for action_name, btn in self.game_over_buttons:
                            if btn.hit(event):
                                if action_name == "play_again":
                                    self.generate_obstacles()
                                    self.reset()
                                elif action_name == "exit":
                                    self.return_to_main_menu = True
                                    self.running = False
                                break
                    action = self.context_menu.handle_click(event)
                    if action:
                        self.handle_menu_action(action)

                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        if self.context_menu.visible:
                            self.context_menu.close()
                        else:
                            items = [
                                {"label": "Pause Game" if not self.paused else "Resume Game", "action": "pause"},
                                {"label": "Reset Game", "action": "reset"},
                                {"label": "Exit Game", "action": "exit"},
                            ]
                            self.context_menu.open(SCREEN_W // 2 - MENU_W // 2, SCREEN_H // 2 - 80, items)
                    elif event.key == pygame.K_r and not self.alive:
                        self.generate_obstacles()
                        self.reset()
                    elif event.key == pygame.K_SPACE:
                        self.sprint_held = True
                    elif not self.paused:
                        if event.key == pygame.K_UP and self.direction != [0, 1]:
                            self.next_direction = [0, -1]
                        elif event.key == pygame.K_DOWN and self.direction != [0, -1]:
                            self.next_direction = [0, 1]
                        elif event.key == pygame.K_LEFT and self.direction != [1, 0]:
                            self.next_direction = [-1, 0]
                        elif event.key == pygame.K_RIGHT and self.direction != [-1, 0]:
                            self.next_direction = [1, 0]

                elif event.type == pygame.KEYUP:
                    if event.key == pygame.K_SPACE:
                        self.sprint_held = False

            if self.alive and not self.paused and time.time() - self.last_tick >= max(0.05, 1.0 / self.speed):
                self.last_tick = time.time()
                self.update_step()
                if self.sprint_held and self.alive:
                    extra_steps = max(0, int(SPRINT_MULTIPLIER) - 1)
                    for _ in range(extra_steps):
                        self.update_step()
                        if not self.alive:
                            break
            self.draw()


def main():
    remembered_name = ""
    while True:
        start = StartScreen(remembered_name).run()
        if not start:
            break
        remembered_name = start.get("name", remembered_name)

        if start["single_player"]:
            game = LocalSinglePlayerGame(start["name"], 1, start.get("lives_setting", DEFAULT_PLAYER_LIVES))
            game.run()
            continue

        if start["multiplayer"]:
            host_server = start["host_server"]
            client_mode = start["client_mode"]
            selected_server = start["server"]

            if client_mode and not selected_server:
                tmp = True
                while tmp:
                    screen.fill(BG)
                    draw_text(screen, "No server selected. Click Find Servers and choose one.", MID, WHITE, SCREEN_W // 2, SCREEN_H // 2 - 20, center=True)
                    draw_text(screen, "Press any key to go back", FONT, DIM, SCREEN_W // 2, SCREEN_H // 2 + 28, center=True)
                    pygame.display.flip()
                    for event in pygame.event.get():
                        if event.type == pygame.QUIT:
                            pygame.quit()
                            sys.exit()
                        if event.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
                            tmp = False
                    clock.tick(FPS)
                continue

            game = MultiplayerGame(
                player_name=start["name"],
                level=start["level"],
                host_server=host_server,
                selected_server=selected_server,
                match_minutes=start.get("match_minutes", 10),
                lives_setting=start.get("lives_setting", DEFAULT_PLAYER_LIVES),
                bot_count=start.get("bot_count", 0),
                bot_difficulty=start.get("bot_difficulty", "Normal"),
            )
            game.run()

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
