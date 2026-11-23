# MessForecast UI design system

Phase 2 of the platform: the interface. This document is the contract every
screen in the product is built against. It is the reusable component library
in written form, so a screen built by one hand matches a screen built by
another.

---

## 1. Two experiences, one system

The platform has two audiences and they do not want the same interface.

| | Console | Tablet |
|---|---|---|
| Who | Mess manager, administrator, finance officer | Kitchen staff, on a wall-mounted tablet |
| Density | Information-rich. Tables before cards. | Three decisions per screen. Large targets. |
| Control height | 32 to 40px | 72px minimum |
| Body text | 14px and up | 20px and up |
| Typing | Typing is fine | Typing is a failure state |
| Contrast | Passes AA for body text | Pushed past AA, large type |
| Hover | Used | Never used, because there is no cursor |

They are **not two design systems**. They are one system at two scales, and
they share one token file, one typeface pairing, one component vocabulary
and one colour meaning. The same figure — turnout, portions to cook,
leftover, cost — reads in both.

**The colour contract.** Colour carries meaning, and the meaning does not
change between surfaces.

| Token | Means |
|---|---|
| `--color-accent` | The model, the forecast, the published plan |
| `--color-accent-2` | Loss: waste, shortfall, the wrong answer |
| `--color-ink` | A number the reader should trust |
| `--color-ink-2` | Supporting text |
| `--color-ink-3` | A hint the reader may ignore |
| `--color-rule` | A structural edge between regions |
| `--color-hair` | A rule inside a region |

A number is never coloured for decoration. Orange means "the model
predicted this". Amber means "this went wrong". Nothing else is coloured.

---

## 2. Tokens

Every colour and every font in the product comes from `static/css/tokens.css`.
No screen may name a colour or a font stack directly. This is not a style
preference: it is what makes the two experiences the same design.

**Type.** The body face is the interface face. The display face is used for
figures only, never for prose.

```
--font-display   figures, numbers, the wordmark
--font-body      everything else
```

**Scale.** `--text-xs` through `--text-4xl`. Body copy is `--text-md` or
larger. On the tablet, body copy is `--text-xl` or larger.

**Space.** `--space-3xs` (2px) through `--space-4xl` (144px). Every margin,
padding and gap uses one of these. No raw lengths.

**Radius.** `--radius-inner`, `--radius-control`, `--radius-card`,
`--radius-pill`. One radius per nesting level.

**Motion.** `--dur-micro`, `--dur-short`, `--dur-long`, and the easing
curves. Only `transform` and `opacity` animate. Never `width`, `height`,
`top` or `left`. Never `transition: all`.

---

## 3. The component library

Two halves. The CSS half is `static/css/components.css`. The template half
is `templates/components/*.html`, included with `{% include %}`.

The template half exists because a Django template cannot pass markup into a
component: `{% include %}` cannot capture body content and Django has no
`{% endinclude %}`. So a partial that needs a body — a panel, a table, a
field — is written as a native `<section class="panel">` in the screen
template, and the partials that need no body (the figure row, the spec
list, the state) are included.

### 3.1 The console family, `.c-*`

| Component | Class | What it is |
|---|---|---|
| Stack | `.c-stack` | Vertical rhythm. `is-tight`, `is-loose` |
| Cluster | `.c-cluster` | Horizontal run of items that may wrap |
| Spaced | `.c-spaced` | A section that needs air above it |
| Grid | `.c-grid` | Two equal columns. `is-3`, `is-4` |
| Split | `.c-split` | Content plus a sticky context column |
| Context | `.c-context` | The right-hand column of a split |
| Page head | `.c-head` | Title, one sentence, actions, side notes |
| Type | `.c-type-display` `.c-type-body` `.c-type-label` | The three voices of the type scale |
| Tabs | `.c-tabs` | Views of the same subject. Scrolls sideways |
| Segment | `.c-segment` | Picks one of a few views |
| Crumbs | `.c-crumbs` | Path, separated by rules not punctuation |
| Figure | `.c-fig` | One figure, set large, with its label |
| Figure row | `.c-figrow` | Four figures divided by hairlines |
| Notice | `.c-banner` | A fact the reader did not have |
| Meter | `.c-meter` | A proportion, as a bar on a track |
| Form | `.c-form` | Vertical form. `is-wide` |
| Form grid | `.c-form-grid` | Fields side by side |
| Field | `.c-field` | Label, control, help, error |
| Fieldset | `.c-fieldset` | A named group of fields |
| Switch | `.c-switch` | A toggle |
| List | `.c-list` | Definition rows, where a table is too heavy |
| Spec | `.c-spec` | A named row with a figure |
| State | `.c-state` | Empty, loading or error, with what to do next |
| Board | `.c-board` | The menu schedule, seven days across |
| Band | `.c-band` | A forecast with its confidence range |
| Range | `.c-range` | The same range, on one line |
| Actions | `.c-actions` | A row of buttons. `is-top` |
| Pager | `.c-pager` | Pagination |

**The list markup.** `.c-list` is a definition list wearing a list's clothes.
The row is the grid, so the markup is `ul > li > div > (dt, dd)`:

```html
<ul class="c-list">
  <li><div><dt>QR scan</dt><dd>5,872 scans</dd></div></li>
</ul>
```

**The figure kinds.** A figure value is normally a number, set in the display
face. When the value is a phrase rather than a number, the figure carries
`kind="text"` and the value steps down a size, so the words stay whole
instead of breaking across three lines.

### 3.2 The older console vocabulary

`app.css` holds the shell and the components that predate this phase. Keep
using them; they are part of the same system.

`.pagehead` · `.panel` `.panelhead` `.panelbody` · `.ledger` · `.toolbar` ·
`.btn` `.btn-ghost` `.btn-quiet` · `.tally` `.tally-item` `.tally-value` ·
`.field` · `.chip` · `.state` · `.empty` · `.skeleton` · `.hint` ·
`.grid-2` · `.rail` · `.topbar`

`.state` is the small status pill with a dot. The block-level empty and
error regions are `.c-state`, which is a different thing and does not carry
the dot.

### 3.3 The tablet family, `.k-*`

`static/css/kitchen.css`. Large buttons (`.k-btn`), large cards (`.k-card`),
large stamps (`.k-stamp`), steppers (`.k-stepper`), tickets (`.k-ticket`),
the day strip (`.k-day`), the brief (`.k-brief`), and the service states
(`.sv-state`, `.sv-goal`, `.sv-open`).

### 3.4 Rules that hold everywhere

1. **Every control has eight states.** Hover, focus, active, disabled,
   visited, plus the three of them on the keyboard path. Focus is always
   visible, instantly, via `:focus-visible` with a `2px` outline.
2. **A panel never holds a panel.** One containment layer.
3. **A list never empties silently.** It shows the empty state, the loading
   state or the error state, and each says what to do next.
4. **Labels are sentence case.** Never tracked capitals, never small caps.
   A label is the body face, one step smaller than the prose around it.
5. **No emoji as icons.** No middle dots joining metadata. No arrows glued
   to link text.
6. **Every animation has a reduced-motion fallback.**
7. **A number is never invented.** Every figure comes from a recorded
   service. Where a figure does not exist, the screen says so.
8. **A table column faces one way.** The header and every cell in it share
   an alignment. A date is a label; a figure is a number.

---

## 4. Charting

Charts are inline SVG, drawn by `static/js/app.js`. No library, no CDN,
because the kitchen tablet has no network.

```html
{{ data|json_script:"chartDataId" }}
<div class="chart" data-chart="bar"
     data-src="chartDataId"
     data-value="waste_cost"
     data-label="week"
     data-prefix="₹"
     data-height="200"
     data-title="Waste cost per week"></div>
```

`data-chart` is `bar`, `line` or `band`. `data-tone` is `loss` for amber and
`model` for orange. The label key is parsed and shortened: an ISO date
becomes "14 Mar".

**The forecast band.** A forecast is not a number, it is a number with a
range around it. `data-chart="band"` draws the range as an area and the
prediction as a line, so the reader sees how much room the kitchen has, not
just a point. The single-line version is `.c-range`.

Two rules the band follows that the other charts do not:

- **The scale is fitted to the range, not to zero.** A band drawn against a
  zero baseline squashes the range into a hairline, and the range is the
  whole point of the chart.
- **The x axis is labelled by day, not by service.** Several services share
  a date, so a label is drawn when the date changes and there is room for it.

The band is filled with `--color-accent-band`, a step stronger than
`--color-accent-wash`, because it carries more meaning than a line chart's
area does.

---

## 5. Screen anatomy

A console screen, in order:

1. `c-head` — the name, one sentence of orientation, the actions that
   belong to that name.
2. A filter bar, when the screen has a window or a hall filter.
3. The figures, ruled rather than tiled.
4. The charts, beside the numbers they explain.
5. The tables. Always last, always the thing you scroll to for detail.
6. The method note, so a number can be argued with.

No screen opens with a marketing line. No screen ends with a newsletter
band. The work is the page.

**One navigation per surface.** The rail is the console's only navigation.
A screen that also carries a tab strip above its content gives the reader
two places to look for the same thing, so the console does not.

---

## 6. The kitchen tablet

The tablet is worked with wet gloves, in a hot room, by someone who cannot
read a paragraph.

- **Targets are 72px.** No exception. A gloved hand misses 40px.
- **Three decisions per screen.** More than three and the operator starts
  reading instead of tapping.
- **No typing.** The number stepper exists. Everything else is a tap.
- **Contrast is pushed past AA.** Large type on near-black.
- **No hover.** The tablet has no cursor, so nothing may depend on one.
- **The sticky action bar** holds Save and Back, always in the same place.
- **The work comes before the explanation.** The operator records what was
  prepared and served first; the reason for the number sits below the form,
  where it can be read once the work is done.

---

## 7. Where the code lives

```
static/css/tokens.css        every colour, font, space, radius, duration
static/css/base.css          reset, page frame, forms, buttons
static/css/app.css           the console shell and the older components
static/css/components.css    the component library
static/css/kitchen.css       the tablet family
static/js/app.js             charts, the rail, filter forms, the toast
templates/components/        the template half of the library
templates/console/           the console screens
templates/dashboard/         the reporting screens
templates/kitchen/           the tablet screens
templates/registration/      sign in and register
```

The catalogue at `/console/design-system/` renders every component in every
state it has. It is the living reference, and it is checked by the same
sweep as every other screen.
