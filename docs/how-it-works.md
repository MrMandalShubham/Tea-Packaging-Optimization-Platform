# How the Optimizer Works — Logic and Math, Explained Simply

This document explains, step by step, how the system turns three numbers —
tea density, pouch weight, and shipment quantity — into a complete packaging
plan. Every figure below comes from one real run (the *reference case*:
density 0.35 g/cm³, 250 g pouches, 100,000 units) and can be checked with a
pocket calculator against what the app displays.

**The whole system in one sentence:**

> It tries every sensible combination of pouch → carton → pallet → container,
> prices each complete plan, and keeps the cheapest one that can physically be
> loaded.

Everything else is detail. The details follow.

---

## 1. The inputs

| Input | Example | What it means |
|---|---|---|
| Tea density | 0.35 g/cm³ | How heavy the tea is for its size. Fluffy white tea ≈ 0.20; dense CTC ≈ 0.35–0.42 |
| Package weight | 250 g | Net tea per pouch (the tea only, not the packaging) |
| Shipment quantity | 100,000 | Total pouches to ship |
| Shape / material / market | square, paper, UK | Pouch geometry, pouch material, destination |

---

## 2. Step 0 — Density gives volume (the only physics)

Weight and volume are linked by a single formula:

```
Volume = Weight ÷ Density
250 g ÷ 0.35 g/cm³ = 714.29 cm³        ← the tea itself ("Product Volume")
```

No packaging decision can change this. 250 g of this tea *will* occupy
714 cm³ wherever it goes.

The pouch must be a little bigger, because tea settles and the pouch needs
slack to seal — the system adds **15% headspace**:

```
714.29 × 1.15 ≈ 821 cm³               ← the pouch's internal volume
```

---

## 3. Step 1 — Pouch shapes: same volume, many boxes

Here is the first key idea: **821 cm³ can take many shapes.**
A cube of 93.7 mm. A tall pouch of 93 × 79.1 × 111.6 mm. A flat one of
117 × 100 × 70 mm. All hold exactly the same tea.

What differs between them is **surface area** — how much packaging material
must be bought. For a rectangular pouch:

```
Surface = 2 × (L·W + L·H + W·H)
```

For the pouch the system eventually chose (93 × 79.1 × 111.6 mm):

```
2 × (73.6 + 103.8 + 88.3) cm² = 531.3 cm²
531.3 cm² × ₹12 per m² (paper)  = ₹0.637 per pouch
```

A mathematical fact: **the cube always has the least surface area** for a
given volume. The cube pouch costs ₹0.632 — half a paisa cheaper. Yet the
system does *not* pick the cube. Why not is the heart of the whole design
(section 8). The system generates roughly a dozen candidate shapes and keeps
all of them in play.

---

## 4. Step 2 — Building a carton

Pouches go into a carton in a grid of **nx × ny × nz**. The chosen plan uses
2 × 4 × 5 = **40 pouches per carton**. Carton size is pure addition —
pouches, plus 2 mm breathing gaps between them, plus the cardboard walls:

```
Inner length = 2 × 93     + 1 gap × 2 mm  = 188 mm
Inner width  = 4 × 79.1   + 3 gaps × 2 mm = 322.4 mm
Inner height = 5 × 111.6  + 4 gaps × 2 mm = 566 mm

Outer = inner + 2 × board thickness (3 mm for 3-ply)
      = 194 × 328.4 × 572 mm
```

Weight: 40 × 0.25 kg of tea + ≈ 0.3 kg of cardboard = **10.3 kg** — light
enough for cheap 3-ply board, and one person can lift it.

The search tries **every grid** from 1×1×1 to 12×12×12 and discards any
carton that breaks a rule: heavier than 25 kg (manual handling limit) or
larger than 800 × 600 × 600 mm.

---

## 5. Step 3 — Stacking cartons on a pallet

A pallet is a flat floor the user picks on the form — **1200 × 1000 mm
industrial** by default, with EUR/EPAL 1200 × 800 and US GMA 48 × 40 in also
offered. The pallet is an *input*, never optimised: the exporter's warehouse
fleet dictates it. What the system decides is everything built on it, and the
whole search — including the baseline it is compared against — adapts to
whichever pallet is selected. (The worked example below uses the default
1200 × 1000.)

Cartons per layer is simple
division, rounded down:

```
Along 1200 mm:  floor(1200 ÷ 194)   = 6
Along 1000 mm:  floor(1000 ÷ 328.4) = 3
                                     → 6 × 3 = 18 cartons per layer
Floor coverage: 18 × (194 × 328.4) ÷ (1200 × 1000) = 95.6%
```

The system also tries the cartons **rotated 90°**, and a **mixed** pattern
that slips rotated cartons into the leftover margin — whichever fits more
wins.

How many layers go on top of each other? The **smallest** of three caps:

1. **Height** — the container's roof budget (next section) allows a pallet up
   to ~1,324 mm: `floor((1324 − 150 mm pallet deck) ÷ 572)` = **2 layers**
2. **Weight** — pallets carry at most 1,000 kg: 18 × 10.3 kg per layer leaves
   plenty of room
3. **Crush** — the bottom carton must survive everything stacked on it
   (section 6)

Result: 18 × 2 = **36 cartons per pallet**, standing
150 + 2 × 572 = **1,294 mm** tall, weighing ~371 kg.

---

## 6. Step 4 — Loading the container (with real-world rules)

A 40-foot high-cube (40HC) is internally 12,032 × 2,352 × 2,698 mm.

**Floor:** the same division trick, now with pallets as the pieces:

```
floor(12032 ÷ 1200) × floor(2352 ÷ 1000) = 10 × 2 = 20 pallets on the floor
```

**Height — with forklift clearance.** Pure geometry once produced a plan with
17 mm between the load and the roof: mathematically valid, impossible to
load. The system therefore reserves **50 mm of working room**:

```
Usable height = 2698 − 50 = 2648 mm
Two pallets stacked: 2 × 1294 = 2588 mm → fits, with 110 mm to spare ✓
```

So pallets go **two high** → 40 pallets per container.

**Crush strength.** Cardboard slowly fails under sustained load. The worst
position is the bottom carton of the bottom pallet. It carries:

```
Its own stack:      (2 layers − 1) × 10.3 kg              = 10.3 kg
The pallet above:   (371 kg + 25 kg pallet) ÷ 18 columns  = 22.0 kg
Total on the bottom carton                                 = 32.3 kg
```

A 3-ply carton safely bears ~35 kg long-term → **passes**. If it had failed,
the search would either upgrade the board or find a flatter carton — in fact,
the 40-pouch carton in flat 2-layer pallets *is* that solution, found
automatically: it keeps cheap 3-ply by keeping the stack load low.

**Container totals:**

```
40 pallets × 36 cartons        = 1,440 cartons per container
1,440 × 40 pouches             = 57,600 pouches per container
100,000 ÷ 57,600 → need        = 2 containers
Space filled by cartons        = 68.8% of the container's volume
```

(100% is impossible for palletized freight: pallets cover at most ~85% of the
floor, and carton heights never divide the roof height exactly. Real-world
palletized loads run 60–75%; this plan sits comfortably in that band.)

---

## 7. Step 5 — The money

Three costs. Nothing hidden:

```
Pouch material : 100,000 pouches × ₹0.637          = ₹63,750
Carton board   : 2,500 cartons  × ₹19.14           = ₹47,850
Freight        : 2 containers   × ₹22,500          = ₹45,000
                                        TOTAL      = ₹1,56,600
```

Freight per container = rate ₹2.5 per nautical mile × 5,000 nm voyage ×
container factor (1.00 for 20GP, 1.65 for 40GP, 1.80 for 40HC). *These rates
are placeholders with the right structure — a client's real contract rates
slot into one constants file.*

Note that costs are charged on the **shipment** (2,500 cartons), never on
container capacity — an early bug charged a 1-pouch order as if it filled the
whole container.

---

## 8. ⭐ The core idea: optimize everything together, not step by step

The obvious approach — pick the best pouch, *then* the best carton for it,
*then* the best pallet — **fails**, and it fails like this:

1. Best pouch alone = the **cube** (least surface area, cheapest paper).
2. Best carton alone = **cram in the most pouches** → hits the 25 kg weight
   limit → produces a **572 mm-tall** carton.
3. That tall carton fits only 2 layers under the height rule → a short
   pallet → only **one** pallet fits vertically in a 2.39 m container →
   **1.1 metres of paid container height ships empty.**

Every step was locally "best". The combined result was **36.9% full
containers** — precisely the disease the client described. This is the
classic trap of greedy optimization: *local best ≠ global best.*

The fix: **evaluate complete plans, not stages.** The search space is:

```
~12 pouch shapes × ~1,700 valid carton grids × 3 container types × 2 stacking
options ≈ 15,000 complete configurations
```

Fifteen thousand is *tiny* for a computer — the full search runs in under a
second — so the system checks **all** of them and the winner is the provable
cost minimum of the model, not an approximation. No machine learning is
needed or wanted here: the physics is exactly known, and arithmetic is
auditable in a way a neural network never is.

This is why the cube loses: it saves ₹500 of paper across the shipment, but
its cartons tile the pallet worse and stack shorter, which eventually costs
tens of thousands in freight. **A pouch's shape is really a freight
decision** — and only a whole-plan search can see that.

---

## 9. The savings claim — measured against an honest baseline

"Saves 27%" is only meaningful if the comparison point is real. The system
therefore models **current practice** independently, as a competent exporter
without an optimizer would work — and prices it with the *same formulas*:

| Decision | Conventional practice | Result |
|---|---|---|
| Pouch | Nearest **stock catalogue size**: 100 × 60 × 150 mm (900 cm³) | Fill ratio only 79% — paid-for air |
| Carton | Stock 400 × 300 × 300 mm box, 40 pouches | 10.47 kg |
| Pallet | Uniform layers, no mixed patterns; **crush-capped at 4 layers** | 9 × 4 = 36 cartons |
| Container | 20GP out of habit, floor-loaded, no double-stacking | 9 pallets → 324 cartons per container |

```
Containers: ceil(2,500 ÷ 324)                        = 8
Pouches   : 100,000 × ₹0.72 (600 cm² of paper)       = ₹72,000
Board     : 2,500 × ₹17.42                           = ₹43,560
Freight   : 8 × ₹12,500                              = ₹1,00,000
                                     BASELINE TOTAL  = ₹2,15,560

SAVING = 2,15,560 − 1,56,600 = ₹58,960  →  27.4%
```

Two fairness rules protect this number:

- **No fudge factors.** An earlier version literally multiplied the AI answer
  by 0.8 and called it "current" — guaranteed savings by construction. It was
  deleted; an automated test now fails if the savings ratio ever looks
  suspiciously constant across different inputs.
- **No strawman.** The modelled human is *competent*: they rotate pallet
  layers, they load container floors properly, and when a stack would crush
  they stack one layer fewer (the free response) rather than buying expensive
  board. Every crutch removed from the baseline was a fake saving removed
  from the headline.

If the exporter's real current figures are entered, they replace the model
entirely and the comparison becomes exact.

---

## 10. Two utilization numbers (deliberately)

The system reports two different "how full" figures because they answer
different questions:

- **Packed % (capacity view)** — how densely the scheme fills one *full*
  container: **68.8%**. Measures the quality of the packing, independent of
  order size.
- **Utilization % (shipment view)** — how much of the *booked* volume holds
  tea: **67.3%**. Lower, because the second container ships part-full
  (1,060 of 1,440 cartons) and freight is paid on the empty part too.

Mixing these up produced past absurdities (a one-pouch order "64% utilized";
a 20GP appearing to out-ship a 40GP), so every metric now belongs to exactly
one view.

---

## 11. What guarantees it's right

Over 240 automated checks assert statements that *must* hold if the logic is
correct, including:

- No two cartons ever occupy the same space; nothing pokes outside its
  container; every plan honours weight, height, clearance, and crush limits.
- The "densest possible" plan is never cheaper than the "cheapest" plan — if
  it ever were, the search is not finding the true minimum.
- The 3D view composes to *exactly* the counts shown in the tables — a
  picture that disagrees with its own numbers is treated as a bug, not art.
- Savings stay within a defensible band (currently 27–53% across pouch
  sizes); a claim above 55% fails the build, because it would not survive a
  packaging engineer's first question.
- The recommendation is **rate-robust**: sweeping freight rates across a 20×
  range changes the money but never the recommended physical plan.

---

## 12. Honest limits

- **₹ figures are indicative** until the client's real material and freight
  rates are loaded; the *relative* comparison and the physical plan are the
  reliable outputs.
- Board crush ratings are conservative defaults (≈ lab strength ÷ 4); a
  specific board choice should be confirmed with supplier data.
- Round pouches are packed as their bounding boxes (honest but pessimistic);
  mixed-SKU containers and multi-leg freight are out of scope.

The full list, with what would change if the client corrected each
assumption, lives in [assumptions.md](assumptions.md).
