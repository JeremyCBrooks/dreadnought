## Dreadnought Roguelike (Vertical Slice)

Python + `python-tcod` sci-fi roguelike. ASCII visuals, FOV shadowcast, procedural dungeons, turn-based combat, environmental hazards, and a strategic galaxy layer.

### Setup (uv + venv + requirements.txt)

```powershell
uv venv .venv
.\.venv\Scripts\Activate.ps1
uv pip install -r requirements.txt
```

### Run the game

```powershell
.\.venv\Scripts\python.exe main.py
```

### Run tests

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ -v
```

### Game flow

**Title** → **Strategic** (star system — pick locations, navigate between systems) → **Briefing** (choose suit) → **Tactical** (dungeon: explore, fight, loot) → reach exit `>` → back to **Strategic**.

Collect 6 navigation units from derelicts across the galaxy to reveal the Dreadnought's location. Board the Dreadnought, extract its reactor core, and return it to your home system to win.

### Controls

#### Tactical mode (dungeon exploration)

| Key | Action |
|---|---|
| Arrows / vi keys (hjklyubn) / numpad | Move (8-directional) |
| `.` or numpad 5 | Wait |
| `g` or `,` | Pick up item |
| `f` | Fire ranged weapon |
| `e` | Interact (containers, switches, reactor cores) |
| `s` | Scan area |
| `x` | Look mode (cursor inspect tiles/entities) |
| `i` | Open inventory |
| `c` | Open cargo management |
| `Shift+Q` | Quit to title |
| `PgUp` / `PgDn` | Scroll message log |

#### Strategic mode (star system navigation)

| Key | Action |
|---|---|
| `Tab` | Toggle focus: locations ↔ star map |
| Arrows / vi keys | Select location or navigate to adjacent system |
| `Enter` | Dock at selected location |
| `m` | Open galaxy map |
| `c` | Open cargo management |
| `Esc` | Quit confirmation |

#### Galaxy map

| Key | Action |
|---|---|
| Arrows | Pan camera |
| `c` | Center on current system |
| `h` | Center on home system |
| `Esc` | Close |

#### Inventory / Cargo

| Key | Action |
|---|---|
| Up / Down | Navigate items |
| `Enter` | Use consumable / transfer item |
| `e` | Equip / unequip |
| `d` | Drop (inventory only) |
| Left / Right | Switch sections (cargo) |
| `Esc` | Close |

### Features

- **Turn-based combat** — melee bump attacks and ranged weapons with ammo and line-of-sight
- **Enemy AI** — 4-state machine (sleeping → wandering → hunting → fleeing) with configurable vision, aggro, pathfinding, and door interaction
- **Environmental hazards** — vacuum, radiation, fire, gas, explosive decompression, low gravity
- **Suit system** — EVA Suit (vacuum/cold) and Hazard Suit (radiation/heat) with resistance pools
- **Equipment** — 2-slot loadout (weapon + scanner/tool), durability, 3-tier scanners
- **Ship systems** — fuel, hull integrity, cargo hold, nav unit tracker
- **Procedural galaxy** — on-demand star system generation, multiple locations per system, deterministic seeding
- **Drift** — when fuel runs out, the ship drifts to a random neighbor, jettisoning cargo
- **Reactor cores** — extractable tile fixtures that convert to fuel; the Dreadnought's core triggers victory
- **Gore & debris** — blood, scorch marks, and debris on ships

### Project structure

```
main.py                          Entry point
debug.py                         Dev flags (god mode, visible all, etc.)
data/
  entities.json                  Enemy / item / scanner / interactable definitions
  db.py                          Data access and name generation tables
  star_types.py                  Star type visuals
  loc_profiles.py                Location type templates
engine/
  game_state.py                  State machine (push/pop/switch) + Engine
  message_log.py                 Scrollable message log
  font.py                        Tileset loading
game/
  entity.py                      Entity + Fighter component
  actions.py                     All action classes (move, melee, ranged, interact, scan, etc.)
  ai.py                          CreatureAI (4-state FSM)
  scanner.py                     Area scanning + NEARBY HUD
  environment.py                 Hazard propagation, decompression
  hazards.py                     Hazard effects, DoT, equipment damage
  consumables.py                 Consumable use (heal, repair, O2)
  loadout.py                     2-slot equipment system
  suit.py                        Suit stats and resistance pools
  gore.py                        Death gore placement
  ship.py                        Ship data (fuel, hull, cargo, nav units)
world/
  galaxy.py                      Procedural galaxy, star systems, locations
  game_map.py                    GameMap with FOV, lighting, entity tracking
  dungeon_gen.py                 Room-and-corridor procedural generation
  tile_types.py                  Numpy tile dtypes
  lighting.py                    Light source propagation
ui/
  title_state.py                 Title screen
  briefing_state.py              Pre-mission briefing + suit selection
  tactical_state.py              Dungeon exploration (core gameplay)
  strategic_state.py             Star system navigation + compass rose
  inventory_state.py             Inventory overlay
  cargo_state.py                 Cargo transfer (personal ↔ ship)
  galaxy_map_state.py            Full-screen galaxy map
  game_over_state.py             Death / victory screen
tests/                           pytest suite (1200+ tests)
```
