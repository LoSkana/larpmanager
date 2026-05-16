---
name: write-larpmanager-tutorial
description: Use when writing or editing tutorials for the LarpManager platform. Covers the HTML content format, URL conventions, writing style, and section structure used across all 26 existing tutorials.
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

**Cross-tutorial links**:
```html
<a href="https://larpmanager.com/tutorials/<slug>/" target="_blank" rel="noopener"><em><strong>Tutorial Name</strong></em></a>
```

## URL Conventions

| Purpose | Pattern |
|---|---|
| Activate event feature | `https://larpmanager.com/redirect/event/manage/features/<slug>/on/` |
| Activate org feature | `https://larpmanager.com/redirect/manage/features/<slug>/on/` |
| Event management page | `https://larpmanager.com/redirect/event/manage/<section>` |
| Event config section | `https://larpmanager.com/redirect/event/manage/config/<slug>` |
| Org management page | `https://larpmanager.com/redirect/manage/<section>` |
| Tutorial link | `https://larpmanager.com/tutorials/<slug>/` |

All management links use `target="_blank" rel="noopener"`.

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
<p><em>One-line description of what this does.</em> To use it, <a href="https://larpmanager.com/redirect/event/manage/features/<slug>/on/">activate the "<Feature>" feature</a>.</p>
<p>Go to the <a href="https://larpmanager.com/redirect/event/manage/<page>"><Page> panel</a> and click "Add" to create a new entry.</p>
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
