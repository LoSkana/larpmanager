---
name: write-larpmanager-tutorial
description: Use when writing or editing tutorials for the LarpManager platform. Covers the HTML content format, URL conventions, writing style, and section structure, and link text rules ("Event > Page" / "Organization > Page") used across the existing tutorials.
---

# Writing LarpManager Tutorials

## What a Tutorial Is

Tutorials are stored in the database as HTML documents. Each tutorial covers one feature area and is written for **event organizers**, explaining how to activate, configure, and use a feature.

The existing tutorials (see `screenshots.md` for the full list with their order) cover: create-organization, player-information (title "Personal Data"), organization-roles, organization-appearance, manage-events, event-roles, event-appearance, promotion, registrations, manage-ticket, registration-form, registration-accounting, payments, characters, character-references, pdf-generation, character-form, character-creation, character-inventory, xp, factions, ensemble, guilds, plots, writing-extras, matchmaker, casting, quests, deadlines, users, user-flags, membership, accounting, checkin, debrief, event-tools, organization-tools, italian-associations, manage-mails.

## Data Structure (JSON export)

```json
{
  "id": "<integer>",
  "name": "Feature Name",
  "slug": "feature-slug",
  "descr": "<html content>",
  "order": "<integer>",
  "created": "YYYY-MM-DD HH:MM",
  "updated": "YYYY-MM-DD HH:MM",
  "deleted": "",
  "deleted_by_cascade": "0"
}
```

## HTML Content Structure

### Mandatory Elements

**Opening paragraph** — one or two sentences explaining what the tutorial covers and when to use it.

**Section headings** use `<h2>`:
```html
<h2>Section Title</h2>
```

**Horizontal rules** `<hr>` separate every major topic. Use them liberally — after each concept, after screenshots that end a section, before new sub-features.

**Screenshots** appear after nearly every step. Use the pattern:
```html
<p><img src="/media/tutorial_screenshots/<order>_<slug>_<nn>.png" alt="<short description>" width="<w>" height="<h>"></p>
```
When writing a new tutorial, use placeholder `[SCREENSHOT: description]` instead of real image tags.

**Notes and clarifications** use italic:
```html
<p><em>Note: this only applies when the Characters feature is active.</em></p>
```

**Field names and key terms** use bold:
```html
<p>Set the <strong>Max Participants</strong> field to 0 for unlimited.</p>
```

## Links

Every page can live in either the **event** dashboard or the **organization** dashboard, so link text must always state the scope first. All links are absolute (`https://...`), end with `/`, use `target="_blank" rel="noopener"`, and wrap the text in `<strong>`.

### Link text rules

| Link to | Text inside the link | Example sentence |
|---|---|---|
| Event page | `Event &gt; <sidebar label>` | `go to <a ...><strong>Event &gt; Discounts</strong></a> and click "New".` |
| Organization page | `Organization &gt; <sidebar label>` | `go to <a ...><strong>Organization &gt; Roles</strong></a>.` |
| Event config section | `Event &gt; Configuration &gt; <section label>` | `In <a ...><strong>Event &gt; Configuration &gt; Experience points</strong></a>, enable ...` |
| Org config section | `Organization &gt; Configuration &gt; <section label>` | `In <a ...><strong>Organization &gt; Configuration &gt; VAT</strong></a>, set ...` |
| Dashboard home | `Event &gt; Dashboard` / `Organization &gt; Dashboard` | `from <a ...><strong>Event &gt; Dashboard</strong></a>.` |
| Feature activation | exact feature name only | `activate the <a ...><strong>Discount</strong></a> feature.` |
| Other tutorial | tutorial name, `<em><strong>` | `see the <a ...><em><strong>Character Sheet</strong></em></a> tutorial.` |
| Section of a tutorial | the `<h2>` text, `<em><strong>` | `see <a ...><em><strong>Player Selection</strong></em></a> below.` |

- **Labels must match the UI exactly**:
  - Sidebar labels: the `name` of `EventPermission`/`AssociationPermission` in `larpmanager/fixtures/event_permission.yaml` / `association_permission.yaml` (e.g. `orga_sensitive` is "Users", `exe_membership` is "Members").
  - Feature names: `name` in `larpmanager/fixtures/feature.yaml` (e.g. "Casting algorithm", "Verification payments", "Organizational fee").
  - Config sections: second argument of `set_section()` in `larpmanager/forms/event.py` / `association.py`, and the URL uses its first argument (e.g. `config/experience/`, not `config/px`).
- **Only the destination goes inside the link**: "go to", "the", "page", "panel", "First", "activate", "feature" and trailing punctuation (`.`, `,`, `:`) stay outside. No leading/trailing spaces inside the link.
- **When the same page exists in both scopes, name both explicitly**: `from <a>Event &gt; Tokens</a> (event expenses) or from <a>Organization &gt; Tokens</a> (organizational expenses)`.
- **Never** use vague text ("see this section", "detailed here", "set the configurations", "Configuration" alone), bare URLs as link text, "X panel"/"X page" labels, possessives ("Organization's Text"), or `Event / X` slash style.
- A feature-activation link points to `.../features/<slug>/on/`; if the sentence refers to the tutorial instead, link the tutorial separately: `If the <a>Casting algorithm</a> feature is active (see the <a><em><strong>Casting</strong></em></a> tutorial), ...`.
- `&gt;` is the separator (ASCII); do not use icons or non-ASCII arrows.

## URL Conventions

| Purpose | Pattern |
|---|---|
| Activate event feature (`overall: false`) | `https://larpmanager.com/redirect/event/manage/features/<slug>/on/` |
| Activate org feature (`overall: true`) | `https://larpmanager.com/redirect/manage/features/<slug>/on/` |
| Event dashboard | `https://larpmanager.com/redirect/event/manage/` |
| Event management page | `https://larpmanager.com/redirect/event/manage/<path>/` |
| Event config section | `https://larpmanager.com/redirect/event/manage/config/<section>/` |
| Org dashboard | `https://larpmanager.com/redirect/manage/` |
| Org management page | `https://larpmanager.com/redirect/manage/<path>/` |
| Org config section | `https://larpmanager.com/redirect/manage/config/<section>/` |
| Tutorial link | `https://larpmanager.com/tutorials/<slug>/` |
| Tutorial section | `https://larpmanager.com/tutorials/<slug>/#<slugified h2 text>` |

- Event pages are always `redirect/event/manage/...`, never `redirect/manage/event/...`.
- Feature scope decides the activation URL: check `overall` in `feature.yaml`.
- `<path>` must match a URL in `larpmanager/urls/orga.py` (without the `<slug:event_slug>/` prefix) or `larpmanager/urls/exe.py`. Verify, e.g.: awards are `experience/awards/`, navigation is `buttons/`, the sheet is `writing/form/`, uploaded expenses are `upload_expenses/`.
- Tutorial section anchors are generated client-side from `<h2>` text (lowercase, spaces to `-`, symbols removed); the target `<h2>` must exist.
- Never link a test/staging instance (e.g. `test.larpmanager.com`) or use relative hrefs.

## Terminology

Use the same word for the same thing everywhere:

| Use | For | Not |
|---|---|---|
| **participant** | someone attending an event | player, attendee |
| **user** | an account on the platform (profile, preferences, membership) | member (unless it is the Membership feature), player |
| **registration** | signing up to an event (noun) | signup, sign-up, sign up |
| **register** / **sign up** | the action (verb) | |
| **session** | one edition of an event, with its dates | run, edition |
| **organization** | the association using LarpManager | association, organisation |

Keep a different word only when it is part of a UI label or feature name (e.g. "Player relationships", "New player" ticket).

## Headings and lists

- `<h2>` headings use **sentence case**: only the first word and proper nouns are capitalized ("Scanning a QR code", "Activating debrief", not "Scanning a QR Code").
- Any tutorial longer than a few paragraphs is split in `<h2>` sections, separated by `<hr>`.
- Lists of fields or options are **always bullet lists**, one field per item, with the label in bold:
```html
<ul>
<li><strong>Name</strong>: short name of the faction.</li>
<li><strong>Presentation</strong>: public description.</li>
</ul>
```
  Never a paragraph of `<strong>Field</strong>: ...<br>` lines.
- Every tutorial ends with a related-tutorials line, linking 2-4 tutorials on neighbouring topics:
```html
<hr>
<p><em>Related tutorials: <a href="https://larpmanager.com/tutorials/<slug>/" target="_blank" rel="noopener"><em><strong>Name</strong></em></a>, ...</em></p>
```

## Writing Style

- **Second person, imperative**: "Go to…", "Click on…", "Activate the…", "Input the following…"
- **Feature activation first**: always start a sub-feature section by telling users to activate it
- **Field-by-field**: when describing a form, list and explain each field
- **Player perspective**: after explaining staff configuration, explain what players will see
- **Short sentences**: one action per sentence
- **No preamble**: get straight to "To do X, go to Y"
- **Present tense**: "a new field appears", not "a new field will appear"; avoid "Now,", "you'll find", "It is possible to"
- **Short paragraphs**: at most ~60 words; split longer ones

## Typical Section Pattern

```html
<h2>Sub-feature name</h2>
<p><em>One-line description of what this does.</em> To use it, activate the <a href="https://larpmanager.com/redirect/event/manage/features/<slug>/on/" target="_blank" rel="noopener"><strong><Feature name></strong></a> feature.</p>
<p>Go to <a href="https://larpmanager.com/redirect/event/manage/<path>/" target="_blank" rel="noopener"><strong>Event &gt; <Sidebar label></strong></a> and click "Add" to create a new entry.</p>
<p>[SCREENSHOT: panel overview]</p>
<p>Define the following values:</p>
<ul>
<li><strong>Field name</strong>: what it does.</li>
<li><strong>Other field</strong>: what it does.</li>
</ul>
<p>[SCREENSHOT: form filled]</p>
<hr>
<p><em>Note: any edge case or dependency on another feature.</em></p>
<hr>
```

## Dependency Notes

When a sub-feature requires another feature to be active, call it out in italic:
```html
<p><em>If both <strong>Progress</strong> and <strong>Assigned</strong> are active, a summary appears mapping assigned characters to progress.</em></p>
```

When a feature changes what players see during signup or on their profile, always include that perspective.

## Screenshots

`screenshots.md` (next to this file) lists what every existing screenshot shows: page URL and crop. Keep it updated when adding, removing, or retaking screenshots.

### Style

- **One consistent scale**: capture at a fixed 1280x800 CSS viewport with device scale factor 2, and never resize crops. In the `<img>`, set `width`/`height` to **half** the PNG pixel size (CSS pixels), so every screenshot shows UI text at the same size as the real page and stays sharp on retina. The tutorial CSS only caps images at `max-width: 100%`; full pixel sizes make small widgets blow up to 2x.
- **Light v22 interface**, default theme, English UI; never mix with old dark-theme shots in the same tutorial.
- **Orientation, then detail**: the first screenshot of a page shows its title and the relevant area (the link text already names the sidebar path, so the sidebar is not included); following ones crop tightly on the form rows, table rows, or widget being described. Pad crops by 8px, enough to avoid cut edges without showing neighbouring elements.
- **Highlight the click target** when the step is "click X" and X is not obvious: one style only, a 3px outline in the theme accent color injected before capture. No arrows, no text on images (they cannot be translated).
- **Skip trivial shots**: a single checkbox, a single select, or a single field whose name is already in bold in the text does not need a screenshot. Fewer, richer images are easier to read and to keep current.
- **Show the state the text describes**: open the dropdown when the text lists its options, check the box the text refers to, run the algorithm before shooting its results. Empty forms for "create new" steps; filled example data for results and player views.
- **Believable demo data**: one fictional setting across all tutorials (organization "Test Organization", event "Test Event", characters Aldric Vane, Mira Solen, ...; players Elena Ricci, Marco Bellini, ...; `@example.com` emails, the standard example IBAN), never placeholder text like lorem ipsum, real people or real accounts. Use the same names in the tutorial text examples. The Create Organization tutorial explains once that these are example names; when a screenshot where the demo names are prominent (top bar, dashboard) appears in a tutorial read on its own, say so in the text.
- **Clean capture**: no cursor, hover tooltips, focus rings, toasts, cookie banners, debug toolbar, or staging markers; animations disabled; fixed dates so shots do not age visibly.
- **Player views** are logged in as a player on the public event pages; manage views as an organizer.
- **Alt text**: short description of what the image shows (e.g. `alt="Faction form"`), for accessibility and for when images fail to load.

### Taking them

Screenshots are produced by Playwright tests in `playwright/` (next to this file), run against the pytest live server
on the isolated test database, so the dev database is never touched:

```bash
source .venv/bin/activate
pytest .claude/skills/write-larpmanager-tutorial/playwright/<group>_shots_test.py -p no:cacheprovider
```

- `lm_shots.py`: the `Shooter` (retina 1280px capture, crop with padding, per-tutorial JSON index), demo-world seeding
  (`seed_base`, `seed_characters`, `seed_factions`, `seed_registrations`, `seed_tickets`, `seed_questions`, ...), and
  helpers: `activate()` (real feature activation URL at the right scope), `set_config()`, `row()` / `row_label()`
  (form rows), `section()` (opens a collapsible config or form section), `banner()` / `content()` (page title and
  body), `menu()` (sidebar entries), `open_select()` (draws a native select as an open dropdown).
- `*_shots_test.py`: one test per tutorial; each `sh.shot(n, targets, alt)` number matches the image number in
  `screenshots.md`.
- `dump_test.py`: saves HTML and a full-page PNG of any page (`DUMP_URLS`, `DUMP_FEATURES`) to find selectors for new
  capture steps. Claude in Chrome can be used for the same purpose on a dev server.
- Output: `tutorial_screenshots/` at the repo root (not committed). A failed crop writes `*_FAILED.html` there.
- Review with a contact sheet (`montage tutorial_screenshots/<order>_*.png ...`), then copy the folder to
  `MEDIA_ROOT/tutorial_screenshots/` on the server. Tutorial images point to `/media/tutorial_screenshots/<file>`, with
  `alt`, `width` and `height` taken from the JSON index (CSS pixels, half the PNG size).

Gotchas:

- Pass the test files explicitly: `pytest.ini` only collects `larpmanager/tests/`, so the folder alone collects nothing.
- The test folder name must contain `playwright`, so `conftest.py` reloads the fixtures for every test.
- Forms that open in a popup have a standalone URL with `?frame=1` (e.g. `test/manage/factions/new/?frame=1`): capture
  that instead of the popup. Rows have ids `#id_<field>_tr`.
- TinyMCE is disabled in test settings: each test module re-enables it with `settings.TINYMCE_DISABLED = False`.
- Native select popups, hover tooltips and OS dialogs are not captured by Playwright: use `open_select()` or skip.
  `<details>` menus open with `el.open = true`.
- Camera pages (check-in scanner): the browser runs with a fake camera; pass `camera=qr_video(png, y4m)` to a
  `Shooter` to feed it a real QR code, so the scan actually happens.
- DataTables split header and body into two tables: crop `.dt-container`, not `table`.
- Many rows are inside collapsed sections: call `section(page, "<label>")` first.
- Activating Membership, Payments or Character creation adds banners for players: the seed marks memberships
  accepted and profiles complete, change them only in the tutorial that explains them.
- Keep `larpmanager/static/node_modules` in sync with `package.json` (`npm install`), or pages using upgraded
  libraries (e.g. the casting solver) break.

## What to Avoid

- Explaining Django or technical implementation details
- Using "the system" for every subject — prefer "LarpManager" or direct "you"
- Skipping the feature activation link — every optional sub-feature must show how to enable it
- Long paragraphs — each paragraph should cover a single action or concept
- Link text that hides the scope, or does not match the sidebar/feature/section name (see **Links**)
- Leftover editor attributes (`data-start`, `data-end`, `data-is-last-node`, ...) from pasted content
- Inline styles (`style="text-align: center"`, `align=`, styled `<span>`), `&nbsp;` padding and empty `<p>&nbsp;</p>` paragraphs left by the editor
- Typographic entities (`&rsquo;`, `&ldquo;`, `&mdash;`): use plain `'`, `"` and `-`; `&euro;` is fine
- "X panel": name the page with a scope link instead (`in <a>Event &gt; Registrations</a>`)
- "a new field will be added:" followed by an image of that single field: name the field in bold instead
- Field names that differ from the UI: copy the label from the form (`verbose_name` / `add_configs` label), e.g. "Disable amount change", not "Disable Change Amount"

## Before Finishing

Run the checker, and fix everything it reports for the tutorials you changed:

```bash
.venv/bin/python .claude/skills/write-larpmanager-tutorial/check_tutorials.py <export.json> [--slug <slug>]
```

It checks bold labels against the UI strings, redirect links against the URLconf, tutorial links and section anchors, image alt/size, banned wording, terminology, heading case, separators and the related-tutorials line. Then check by hand:

Check every link in the tutorial:
1. Scope prefix present (`Event &gt;` / `Organization &gt;`) for management and config links.
2. Label matches the fixture/form name exactly.
3. The target resolves: strip `https://larpmanager.com/redirect/`, and for `event/...` prefix an event slug, then resolve it against the Django URLconf.
4. Feature activation URL scope matches the feature's `overall` flag.
