# Portal Deep Space Background — Design Spec
**Date:** 2026-05-01
**Scope:** `web/static/portal.html` only

## Summary

Add a "deep space" background to the web portal that mirrors the in-game system view aesthetic: a blue-white star in the top-right corner, soft nebula clouds, and scattered static stars. Font, layout, and color scheme are unchanged.

## Visual Design

### Background (body)

A single layered `background` CSS property on `body`:

```css
background:
  radial-gradient(circle at 96% 2%,
    rgba(255,255,255,1)    0%,
    rgba(220,235,255,1)    2%,
    rgba(160,200,255,0.95) 5%,
    rgba(80,140,255,0.85)  11%,
    rgba(30,70,200,0.6)    20%,
    rgba(10,30,100,0.3)    32%,
    transparent            52%
  ),
  radial-gradient(ellipse at 100% 0%,
    rgba(80,140,255,0.14)  0%,
    rgba(20,60,180,0.06)   40%,
    transparent            68%
  ),
  radial-gradient(ellipse at 20% 55%,
    rgba(5,30,45,0.6)   0%,
    rgba(3,18,35,0.35)  30%,
    transparent         60%
  ),
  radial-gradient(ellipse at 60% 70%,
    rgba(25,5,50,0.5)   0%,
    rgba(15,3,35,0.25)  35%,
    transparent         60%
  ),
  radial-gradient(ellipse at 85% 20%,
    rgba(20,50,120,0.12) 0%,
    transparent          40%
  ),
  #060810;
```

### Starfield

A CSS `::before` pseudo-element on `body`:
- `position: fixed; inset: 0; pointer-events: none; z-index: 0`
- `box-shadow` list of ~25–30 static white/blue-white dots
- Three brightness tiers: bright (opacity ~0.85–0.9), mid (opacity ~0.4–0.5), faint (opacity ~0.25–0.3)
- Dot sizes: 1px (most), occasional 2px for brighter stars
- No animation, no JS

All existing portal content must sit on `z-index: 1` or higher so it renders above the starfield pseudo-element.

### User Bar

The `.user-bar` element (pilot name + Logout button) sits in the header, overlapping the bright star corona. Fix contrast with a dark pill backdrop:

- `background: rgba(0, 0, 0, 0.45)`
- `border: 1px solid rgba(255, 255, 255, 0.07)`
- `padding: 0.2rem 0.6rem`
- Pilot name color: `#c0d4f0` (lifted from `#8af` for legibility)
- Logout button color: unchanged (`#8af`)

## Files Changed

| File | Change |
|------|--------|
| `web/static/portal.html` | Add ~25–30 lines of CSS to existing `<style>` block. No HTML or JS changes. |

## Out of Scope

- `web/static/index.html` (login page) — no change
- `web/static/play.html`, `web/static/watch.html` — no change
- Animations, JS starfield, canvas elements
- Font, layout, or color scheme changes
