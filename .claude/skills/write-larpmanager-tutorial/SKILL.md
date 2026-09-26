---
name: write-larpmanager-tutorial
description: Use when writing or editing tutorials for the LarpManager platform. Covers the HTML content format, URL conventions, writing style, and section structure, and link text rules ("Event > Page" / "Organization > Page") used across the existing tutorials.
---

# Writing LarpManager Tutorials

## What a Tutorial Is

Tutorials are stored in the database as HTML documents. Each tutorial covers one feature area and is written for **event organizers**, explaining how to activate, configure, and use a feature.

The 26 existing tutorials cover: registrations, users, manage-events, accounting, event-appearance, player-information, registration-accounting, character-writing, character-creation, characters, create-organization, manage-mails, deadlines, quests, casting, plots, factions, payments, registration-form, manage-ticket, event-roles, organization-roles, organization-appearance, advanced-features, character-form, xp.

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
<p><img src="/media/tinymce_uploads/1/<hash>.png" alt="" width="<w>" height="<h>"></p>
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

## Writing Style

- **Second person, imperative**: "Go to…", "Click on…", "Activate the…", "Input the following…"
- **Feature activation first**: always start a sub-feature section by telling users to activate it
- **Field-by-field**: when describing a form, list and explain each field
- **Player perspective**: after explaining staff configuration, explain what players will see
- **Short sentences**: one action per sentence
- **No preamble**: get straight to "To do X, go to Y"

## Typical Section Pattern

```html
<h2>Sub-Feature Name</h2>
<p><em>One-line description of what this does.</em> To use it, activate the <a href="https://larpmanager.com/redirect/event/manage/features/<slug>/on/" target="_blank" rel="noopener"><strong><Feature name></strong></a> feature.</p>
<p>Go to <a href="https://larpmanager.com/redirect/event/manage/<path>/" target="_blank" rel="noopener"><strong>Event &gt; <Sidebar label></strong></a> and click "Add" to create a new entry.</p>
<p>[SCREENSHOT: panel overview]</p>
<p>Define the following values:</p>
<p><strong>Field Name</strong>: What it does.<br><strong>Other Field</strong>: What it does.</p>
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

## What to Avoid

- Repeating the same screenshot description in alt text (leave `alt=""`)
- Explaining Django or technical implementation details
- Using "the system" for every subject — prefer "LarpManager" or direct "you"
- Skipping the feature activation link — every optional sub-feature must show how to enable it
- Long paragraphs — each paragraph should cover a single action or concept
- Link text that hides the scope, or does not match the sidebar/feature/section name (see **Links**)
- Leftover editor attributes (`data-start`, `data-end`, `data-is-last-node`, ...) from pasted content

## Before Finishing

Check every link in the tutorial:
1. Scope prefix present (`Event &gt;` / `Organization &gt;`) for management and config links.
2. Label matches the fixture/form name exactly.
3. The target resolves: strip `https://larpmanager.com/redirect/`, and for `event/...` prefix an event slug, then resolve it against the Django URLconf.
4. Feature activation URL scope matches the feature's `overall` flag.
