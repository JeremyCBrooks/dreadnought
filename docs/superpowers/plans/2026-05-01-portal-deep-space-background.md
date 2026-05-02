# Portal Deep Space Background Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a blue-white star, nebula clouds, and static starfield to `web/static/portal.html` as a pure-CSS background that matches the in-game system view aesthetic.

**Architecture:** All changes are CSS-only inside the existing `<style>` block in `portal.html`. The star and nebulae are layered `radial-gradient` values on `body`. The starfield is a `body::before` pseudo-element using the CSS `box-shadow` star trick. `isolation: isolate` on `body` creates a stacking context so the pseudo-element z-index is well-defined.

**Tech Stack:** CSS3 (radial-gradient, box-shadow, isolation, position: fixed)

---

### Task 1: Add space background to body

**Files:**
- Modify: `web/static/portal.html` — `<style>` block, `body` rule

The current `body` rule is:
```css
body { background: #0a0a0f; color: #ccc; font-family: monospace; padding: 2rem; }
```

- [ ] **Step 1: Replace the body background and add isolation**

Replace the existing `body` rule with:

```css
body {
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
  color: #ccc;
  font-family: monospace;
  padding: 2rem;
  min-height: 100vh;
  isolation: isolate;
}
```

Note: `isolation: isolate` establishes a stacking context on body so that `body::before` with `z-index: 0` stays behind header/section content. `min-height: 100vh` ensures the gradient covers the full viewport even when content is short.

- [ ] **Step 2: Open portal.html directly in browser and verify**

Open `web/static/portal.html` in a browser (file:// URL is fine for CSS verification). You should see:
- Deep dark blue-black background (`#060810`)
- A bright white/blue glowing star in the top-right corner with a blue corona
- Soft teal nebula cloud in the left-center area
- Soft dark-purple nebula cloud in the lower-center area
- A faint blue halo bleeding from the top-right

The portal UI chrome (header, sections) should render normally on top of the background.

- [ ] **Step 3: Commit**

```bash
git add web/static/portal.html
git commit -m "feat: add deep space background gradients to portal"
```

---

### Task 2: Add static starfield via body::before

**Files:**
- Modify: `web/static/portal.html` — `<style>` block, add `body::before`, `header`, `section` rules

The starfield uses the CSS box-shadow star trick: a 1×1 pixel element at the top-left corner of the viewport, with each star as a `box-shadow` entry offset to its screen position.

- [ ] **Step 1: Add body::before rule for starfield**

Add these rules inside the `<style>` block, after the `body` rule:

```css
body::before {
  content: '';
  position: fixed;
  top: 0;
  left: 0;
  width: 1px;
  height: 1px;
  border-radius: 50%;
  z-index: 0;
  pointer-events: none;
  box-shadow:
    /* bright stars */
    45px  80px  0 0px rgba(220,235,255,0.9),
    190px 35px  0 1px rgba(230,240,255,0.9),
    85px  230px 0 0px rgba(220,235,255,0.85),
    320px 140px 0 1px rgba(230,235,255,0.9),
    60px  440px 0 0px rgba(225,240,255,0.85),
    155px 370px 0 1px rgba(220,235,255,0.9),
    420px 195px 0 0px rgba(230,240,255,0.85),
    50px  580px 0 1px rgba(225,235,255,0.9),
    /* mid stars */
    110px 95px  0 0px rgba(185,205,255,0.5),
    275px 55px  0 0px rgba(185,205,255,0.45),
    175px 195px 0 0px rgba(185,205,255,0.5),
    35px  315px 0 0px rgba(185,205,255,0.45),
    485px 130px 0 0px rgba(185,205,255,0.5),
    360px 290px 0 0px rgba(185,205,255,0.45),
    130px 490px 0 0px rgba(185,205,255,0.5),
    220px 545px 0 0px rgba(185,205,255,0.45),
    500px 410px 0 0px rgba(185,205,255,0.5),
    70px  660px 0 0px rgba(185,205,255,0.45),
    340px 705px 0 0px rgba(185,205,255,0.5),
    445px 560px 0 0px rgba(185,205,255,0.45),
    /* faint stars */
    20px  160px 0 0px rgba(160,180,230,0.3),
    145px 250px 0 0px rgba(160,180,230,0.28),
    300px 375px 0 0px rgba(160,180,230,0.3),
    195px 105px 0 0px rgba(160,180,230,0.28),
    425px 255px 0 0px rgba(160,180,230,0.3),
    95px  620px 0 0px rgba(160,180,230,0.28),
    260px 700px 0 0px rgba(160,180,230,0.3),
    470px 345px 0 0px rgba(160,180,230,0.28);
}
```

- [ ] **Step 2: Lift header and section above the starfield layer**

Update the existing `header` and `section` rules to add positioning so they stack above `z-index: 0`:

```css
header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 2rem;
  border-bottom: 1px solid #333;
  padding-bottom: 1rem;
  position: relative;
  z-index: 1;
}

section {
  margin-bottom: 2rem;
  position: relative;
  z-index: 1;
}
```

- [ ] **Step 3: Refresh browser and verify**

Reload `web/static/portal.html`. You should see:
- 28 scattered white/blue-white dots of varying brightness spread across the page
- Stars are static (no movement)
- Stars appear behind all UI elements (header, sections, table rows)
- Stars appear in front of the gradient backgrounds (visible against the dark space areas)

If stars are invisible or appear on top of UI: check that `body` has `isolation: isolate` and that `header`/`section` have `position: relative; z-index: 1`.

- [ ] **Step 4: Commit**

```bash
git add web/static/portal.html
git commit -m "feat: add static CSS starfield to portal via body::before box-shadow"
```

---

### Task 3: Update user bar styling

**Files:**
- Modify: `web/static/portal.html` — `<style>` block, `.user-bar` rule

The `.user-bar` sits in the header, right-aligned, overlapping the bright blue star corona. The current rule is:
```css
.user-bar { display: flex; align-items: center; gap: 1rem; color: #8af; }
```

The `color: #8af` applies to the username span. The Logout `<button>` inside it inherits the `button` rule (`color: #6af`) so it is unaffected.

- [ ] **Step 1: Update .user-bar rule**

Replace the existing `.user-bar` rule with:

```css
.user-bar {
  display: flex;
  align-items: center;
  gap: 1rem;
  color: #c0d4f0;
  background: rgba(0, 0, 0, 0.45);
  border: 1px solid rgba(255, 255, 255, 0.07);
  padding: 0.2rem 0.6rem;
}
```

Changes:
- `color` lifted from `#8af` to `#c0d4f0` for legibility against the blue star glow
- Dark semi-transparent pill backdrop added
- Thin near-invisible border for definition

- [ ] **Step 2: Refresh browser and verify**

Reload `web/static/portal.html`. Check:
- Username text is clearly readable against the blue star corona in the top-right
- Logout button remains visible (it uses the `button` rule color `#6af`, unaffected)
- The dark pill is subtle — not a hard box, just enough to separate text from background
- The pill does not look out of place against the nebula areas (lower on the page has no star glow, pill should still look fine there)

- [ ] **Step 3: Run the full server and do a logged-in end-to-end check**

Start the dev server:
```bash
cd F:/dev/gamedev/dreadnought
.venv/Scripts/activate
uvicorn web.main:app --reload
```

Navigate to `http://localhost:8000`, log in, and verify the portal page renders correctly with a real username displayed.

- [ ] **Step 4: Commit**

```bash
git add web/static/portal.html
git commit -m "feat: dark pill backdrop on portal user bar for star-glow contrast"
```
