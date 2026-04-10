![image alt](https://github.com/Mustafa-A-Jasim/Snake-Battle-Arena/blob/b4522ab28afd422a98c8738cb7d45b107317d89f/Screenshot%204.jpeg)

# Snake Battle Arena

(SnakeGame) Snake Battle Arena Game is a LAN multiplayer Snake with single‑player progression, bots, bonus food, and a modern HUD.

## Quick Start
1. Install Python 3.10+.
2. Install dependencies:
   ```
   pip install pygame
   ```
3. Run the game:
   ```
   python "Snake Battle Arena v3.8.py"
   ```

## Controls
- Arrow keys: Move
- Space: Sprint (3x speed)
- Tab (multiplayer): Hold to show live standings
- Right click / Esc: Open in‑game menu

## Single Player
- Score 0–19 = Level 1, 20–39 = Level 2, 40–59 = Level 3, 60–79 = Level 4, 80+ = Level 5
- Game completes at Level 5 (score 80)
- Normal food = +1 point
- Bonus food = +5 points and +5 snake length

## Multiplayer (LAN)
- Host a game on one PC, join from others on the same network
- Optional device players (bots) with difficulty selection
- Match timer and lives settings
- Lobby with countdown start
- Final results page with ranking, score, lives, deaths, and status

## Bonus Food
- Spawns after every 4 normal foods **eaten by the same player**
- Any player can collect it once it appears
- Disappears after a short time if not collected

## Versions
- Latest gameplay file: `Snake Battle Arena v3.8.py`
- Earlier versions are kept for history and rollback

## Notes
- Scores are stored locally in `snake_scores_lan.json`
- LAN discovery uses UDP broadcast; some networks may block it

