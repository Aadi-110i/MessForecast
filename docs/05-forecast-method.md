# How the forecast is worked out

*This document is for the mess manager. It contains no code and no mathematics beyond
"times" and "percentages". If you read nothing else, read this.*

---

## The short version

Every morning the system looks at how many students came to each meal recently, works out
what a normal day looks like, adjusts for the day of the week and for anything unusual
happening on the calendar, and tells you how many portions to cook.

It also tells you **how sure it is**. Every forecast comes with a range — "between 460 and
540" — and that range is not a guess: it is measured from how wrong the system has actually
been recently.

---

## The five steps

### Step 1 — Take the calendar out of the history

Suppose a festival week brought 25% more students than usual, and a vacation week brought
70% fewer. If the system learned from those weeks without adjustment, it would conclude
that "week 40 was busy" and "week 43 was quiet" — which is true but useless, because next
year those weeks will mean something else.

So before anything else, each past meal is divided by the effect of whatever was on the
calendar that day. A festival day becomes "a normal day that happened to have 25% more
people", and a vacation day becomes "a normal day". What is left is the underlying rhythm
of the mess.

### Step 2 — Find the normal level, leaning on recent weeks

The system then takes an average of that adjusted history. It does not weight every week
equally: a week from two months ago counts about 72% as much as the week before last,
because conditions change — a new block of students moves in, the canteen next door opens,
the college changes its attendance rule.

That weighted average is the **normal level** for that hall and that meal.

### Step 3 — Adjust for the day of the week

Averages hide weekly rhythm. Friday and Saturday are busy — students stay on campus rather
than going home. Monday is quiet. The system compares the target day of the week against
the same day of the week in the past and works out a factor: "Sundays run at 80% of a
normal day", "Saturdays run at 112%".

**A factor built on two past Sundays is not trusted as much as one built on twenty.** So if
there is little evidence, the system pulls the factor back towards "no difference" rather
than acting on a shaky number. It would rather be slightly wrong on average than confidently
wrong on the day it matters.

### Step 4 — Adjust for anything on the calendar, and for a slow trend

Two more adjustments:

* **Calendar.** Anything on the calendar for that day — an exam period, a festival, a
  holiday, a vacation — multiplies the estimate. If the technical festival is on and it
  usually lifts lunch by 22%, the lunch forecast goes up by 22%.
* **Trend.** If attendance has been slowly rising or falling over the past few weeks, that
  is carried forward — but gently, and with a hard limit. A six-week history cannot support
  a steep trend, and a sudden jump in the data usually means something has changed in the
  world, not that the line has a new slope.

### Step 5 — Say how sure you are

The system replays its own history. For each past meal, it asks: *if I had only known
everything up to that day, what would I have predicted?* Then it compares that prediction
with what actually happened.

That replay is what produces the confidence range. If the system's past predictions were
usually within about 40 students of the truth, the range it publishes is 40 students wide
(adjusted for how confident the 80% level is).

**The range is measured, not assumed.** If the system's track record is poor, the range
widens. If it has been very accurate, the range tightens. You can watch it change week by
week on the accuracy page.

---

## A worked example

Lunch at North Block Mess on a Tuesday in November.

| | |
|---|---|
| Normal level for this hall and meal | 520 students |
| Tuesdays run slightly quieter than average | × 0.96 |
| A technical festival is on | × 1.22 |
| A slow downward trend | − 3% |
| **Forecast** | **520 × 0.96 × 1.22 × 0.97 ≈ 590 students** |
| Range, based on how wrong it has been recently | 545 to 635 |

The kitchen is then told to cook for **590 students plus the margin this hall allows**
(8% by default, configurable per hall). The ingredient list follows from the recipes.

---

## What the system says out loud

Every forecast stores a sentence explaining itself. The real output for a service looks
like this:

> **Lunch at North Block Mess on Tuesday 10 Nov 2026: we expect about 592 students.**
> Working: over the last 8 weeks this service has been running at roughly 540 students once
> festivals and exam weeks are removed. Tuesdays specifically run 4% quieter than that
> average, so the weekday has been taken into account. The Technical Festival is expected to
> pull attendance up by 22%. Uncertainty: our forecasts for this hall have been out by about
> 41 portions on a typical day recently (average error 6.8%), so a sensible planning range
> is 541 to 643 portions.

That text is on the kitchen screen. If the number looks wrong to the cook, the sentence
above it says which part of it is responsible.

---

## What it does **not** do

Being straight about the limits is part of the method:

* **It does not know about a canteen opening next door.** It learns from what happened
  before, so a sudden permanent change in demand takes a few weeks to show up.
* **It is not a prediction of individual behaviour.** It is an estimate of how many people
  will come, and it is wrong sometimes. The range tells you how wrong it has been.
* **It does not replace the cook.** The service-level setting decides how much extra the
  kitchen is willing to cook to avoid running out. That is a kitchen decision, and the
  forecast only supplies the middle of the range.
* **It does not learn from one week.** There is a deliberate minimum of six past services
  before the model will say anything. Before that, it says so and gives a wide range.

---

## The upgrade path

If the mess keeps running this for a term — six to twelve months of real data — the same
history that feeds this method can feed a learned model (gradient boosting on attendance
with weather, event and menu features). That is a genuine improvement worth making, and
it is worth making *after* the data exists, not before.

The reason it is safe to swap is that the forecasting engine is one self-contained module:
it takes observations and returns a forecast, and everything around it — the planning, the
costing, the reporting, the screens — is unchanged by how the number was produced.
