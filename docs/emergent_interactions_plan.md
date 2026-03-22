# Emergent Interactions Plan — Dreadnought

## Context
Roguelikes thrive on systemic interactions between player, NPCs, items, and environment. Dreadnought already has a strong foundation (decompression physics, hazard overlays, AI state machine, equipment/durability, organic vs mechanical entities). This plan adds a batch of interactions that combine existing systems to create emergent, surprising gameplay with minimal new infrastructure.

---

## Interaction List (Priority Order)

### Tier 1 — High impact, builds on existing systems directly

#### 1. Enemy Item Carrying, Usage & Drops
**Enemies carry items, use them tactically, and drop them on death.**

- **Carrying**: Enemies get an `inventory` list (like the player). Populated at spawn from loot tables per enemy type.
  - Pirates: med-kits, melee weapons (bent pipe, stun baton), ranged weapons (blaster), O2 canisters
  - Mech Pirates: repair kits, ranged weapons
  - Bots/Drones: repair kits only
  - Rats: nothing
- **Usage (AI integration)**: New AI decision layer checked each turn before movement:
  - Heal: if HP < 50% and carrying med-kit, random chance to use it (organic only)
  - Repair: if carrying repair kit and has damaged equipment, random chance to use it (mechanical)
  - Equip: enemies spawn randomly with weapons pre-equipped (options are no weapon, ranged weapon or melee weapon); affects their `fighter.power` or enables ranged attacks
  - Ranged attack: enemies with ranged weapons fire at player when in range + LOS (instead of always closing to melee)
- **Drops**: On death, all inventory items drop to the ground at the death tile (or nearest walkable). Uses existing `DropAction` / item placement logic.
- **Scanner integration**: Tier 2+ scanners show enemy equipment; Tier 3 shows full inventory.

**Key files**: `data/enemies.py`, `game/ai.py`, `game/actions.py`, `game/entity.py`, `game/gore.py` (drop on death), `game/scanner.py`

#### 2. Enemy Pickpocketing / Item Stealing
**Some enemies steal non-equipped items from the player on adjacent hit.**

- **Which enemies**: Pirates only (organic, smart, thematic — they're pirates!)
- **Trigger**: On a successful melee hit against the player, % chance (e.g., 20%) to steal a random non-equipped item from `player.inventory` (skip items in loadout slots)
- **Stolen item**: Transferred to the enemy's inventory. Message: "The Pirate snatches your [item]!"
- **Recovery**: Kill the pirate → item drops with their other loot
- **Fleeing with loot**: If a pirate has stolen items and hits flee threshold, they prioritize fleeing (maybe slight boost to flee urgency). They're trying to escape with the goods.
- **Scanner**: Tier 3 scanner reveals stolen items on enemies
- **Counterplay**: Keep loadout full (equipped items can't be stolen). Stay at range. Kill thieves before they flee.

**Key files**: `game/ai.py`, `game/actions.py` (MeleeAction or new steal check), `game/entity.py`, `game/loadout.py` (check `has_item`)

#### 3. Gas Ignition (Gas + Ranged Shot = Explosion)
**Firing a ranged weapon through or into a gas hazard zone ignites it.**

- Ranged projectile path checked against gas hazard overlay
- If any tile along the path (or the target tile) has gas, convert all connected gas overlay tiles to explosive hazard
- Apply explosive damage to all entities on those tiles
- Clear gas overlay after detonation
- Enemies with ranged weapons can accidentally ignite gas too
- Message: "The gas ignites!" + explosion effects

**Key files**: `game/actions.py` (RangedAction), `game/environment.py`, `data/hazards.py`, `game/hazards.py`

#### 4. Sound Propagation / Noise
**Actions generate noise that can wake sleeping enemies.**

- Noise levels: ranged weapon = loud (radius ~12), door toggle = medium (radius ~5), melee hit = quiet (radius ~3), movement = silent
- Sleeping enemies within noise radius roll to wake (compare noise vs `sleep_aggro_distance`)
- Explosive decompression = max noise, wakes everything on the map
- Explosion (gas ignition, explosive hazard) = loud
- Creates stealth gameplay: melee-only runs, careful door management, weighing ranged convenience vs noise cost

**Key files**: `game/ai.py` (sleep→wake logic), `game/actions.py` (emit noise on actions), `game/environment.py` (decompression noise)

#### 5. Door Crush
**Closing a door on an entity deals damage and stuns.**

- `ToggleDoorAction`: when closing, check for entity on door tile
- If entity present: deal structural damage (2 HP), entity loses next turn (stunned)
- Works both ways — enemies with `can_open_doors` could crush the player
- Message: "The door slams on the [entity]!"

**Key files**: `game/actions.py` (ToggleDoorAction)

---

### Tier 2 — Strong interactions, slightly more infrastructure

#### 6. Electric Hazard Stuns Mechanicals
- Mechanical enemies hit by electric hazard: stunned for 1 turn (skip next action)
- Organic enemies: normal damage only
- Player equipment damage still applies to both

**Key files**: `game/hazards.py`, `game/ai.py` (stun state or skip turn)

#### 7. Vacuum Kills Organics / Spares Mechanicals
- Organic enemies in vacuum take suffocation damage (1 HP/turn, like player without suit)
- Mechanical enemies: immune to vacuum damage, still affected by decompression pull
- Creates tactical hull breach decisions based on enemy composition

**Key files**: `game/environment.py`, `game/entity.py`

#### 8. Darkness Weaponization
- Extracting reactor core removes light → area goes dark
- Creatures can only detect player within their `vision_radius` AND if the tile is lit or within close range (e.g., 3 tiles)
- Dark rooms effectively reduce enemy aggro range
- Scanner still works in darkness

**Key files**: `game/ai.py` (vision check), `world/game_map.py` (lighting), `game/actions.py` (TakeReactorCoreAction)

#### 9. Hull Patch Seals Breaches
- Implement the existing hull_repair consumable
- Using it adjacent to a hull_breach tile: converts breach back to wall, removes vacuum source, recalculates hazard overlay
- Tactical loop: breach hull → decompression kills enemies → patch hull → reclaim area

**Key files**: `game/consumables.py`, `game/environment.py`, `world/tile_types.py`

---

### Tier 3 — Flavor / polish

#### 10. Explosive Chain Reactions
- Explosive damage on a tile with an unscanned interactable triggers that interactable's hazard
- Crates with explosive hazards chain-react to adjacent crates

#### 11. Low Gravity + Decompression Amplification
- Low gravity increases decompression pull range (15 vs 10) and tiles-per-step (5 vs 3)

#### 12. Radiation Mutates Organics
- Organic enemies surviving N turns in radiation get stat buff (+1 power or +2 max HP)

#### 13. Gore Attracts Rats
- Rats pathfind toward gore tiles, creating a "scavenger" behavior

#### 14. Damaged Weapon Backfire
- Firing a damaged ranged weapon: % chance to deal damage to the wielder instead

---

## Implementation Order Recommendation

1. **Enemy inventories + drops** (foundation for everything else)
2. **Enemy item usage in AI** (healing, ranged attacks)
3. **Enemy stealing** (pirate flavor, pairs with inventory)
4. **Gas ignition** (quick win, dramatic moments)
5. **Door crush** (small, self-contained)
6. **Sound/noise** (enriches stealth gameplay)
7. Remaining Tier 2 & 3 in any order

## Verification
- Each interaction gets tests written FIRST (per project TDD convention)
- Test that interactions compose: e.g., pirate steals item → player kills pirate → item drops → player picks up
- Test edge cases: enemy uses last med-kit then dies (nothing to drop), steal from empty inventory (no-op), gas ignition with entities in blast zone
- Manual playtesting for feel: are pirate thieves annoying or fun? Is gas ignition too powerful? Is noise radius balanced?
