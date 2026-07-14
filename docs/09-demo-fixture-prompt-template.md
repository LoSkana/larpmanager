# Prompt template: new interactive demo (LarpManagerDemoType)

Reusable prompt skeleton for commissioning another topic demo, modeled on the
Experience demo (`larpmanager/fixtures/demos/experience_demo.py`). Fill in the
bracketed parts and hand it to Claude Code.

## Prompt skeleton

```
In larpmanager/fixtures/demos create a fixture for a template association
and LarpManagerDemoType showcasing the [FEATURE NAME] feature.

Sidebar: restrict to [feature-specific orga_*/exe_* permission slugs] plus
whatever character/registration sidebar is needed to reach it.

Content: [describe the domain-specific setup — the equivalent of "3 races,
3 classes, 10 abilities" for this feature: what entities, how many, what
relationships between them].

Showcase these mechanics of the feature: [list every distinct rule type the
feature supports — e.g. for Experience: prerequisites, modifiers, criteria,
computed rules; for another feature the list will differ].

Pre-populate: [N] characters already created, played by [N] other players,
already signed up[, divided into factions if relevant].

Add LarpManagerDemoHint entries to guide the user through the golden path:
[event page] -> [register] -> [create character] -> [use the feature] ->
[manage the feature as organizer].

Ask me whatever questions you need to fully understand the feature's data
model before proposing a content plan.
```

## Why each part is there (lessons from the Experience demo)

- **"Ask me whatever questions you need"** — the feature's model graph (M2M
  vs FK, AND/OR semantics of requirement fields, whether a mechanic is gated
  by an `EventConfig` flag) is never obvious from the feature name alone. Let
  Claude explore the models first, then negotiate the content plan with you
  before writing code — cheaper to correct a spec than a fixture.
- **Sidebar restriction slugs** — grep `larpmanager/fixtures/event_permission.yaml`
  / `association_permission.yaml` for the feature's slugs before promising a
  sidebar list; don't guess names.
- **"Showcase these mechanics"** — enumerate every distinct rule/relationship
  type the feature's models support (prerequisite chains, cost overrides,
  conditional bonuses, computed/derived fields, etc.) so the fixture doesn't
  accidentally skip one. For Experience this was: ability-to-ability
  prerequisites, character-option prerequisites, modifiers (conditional cost
  override), criteria (conditional XP bonus), rules (computed character
  fields).
- **Pre-populated characters/players/registrations** — makes the demo feel
  "lived-in" immediately instead of showing an empty event; also gives the
  hint flow ("go create a character") something to contrast against
  ("...or look at this one that already exists").
- **Check the clone engine** — `larpmanager/utils/services/demo.py:clone_association()`
  is a generic FK/M2M copier, but it only walks models it explicitly imports
  and calls `_copy_all(...)` on. Any new model family introduced by the
  showcased feature (like `AbilityExp` & friends for Experience) must be
  added there too, or the fixture's data silently vanishes when a real demo
  instance is spun up from the template. This is easy to miss because the
  fixture-loading command (`load_demos`) works fine on its own — the gap only
  shows up when you actually run `clone_association()` end to end. Verify
  with a manual clone in `manage.py shell`, not just by loading the fixture.
- **Idempotency** — `build_<feature>_demo()` should `get_or_create`/short-circuit
  on the `LarpManagerDemoType` slug so `load_demos` is safe to re-run.

## Checklist before declaring a new demo done

1. `python manage.py load_demos` runs clean twice in a row (idempotent).
2. Manually call `clone_association(demo_type, "test-slug", 1)` in a shell
   and confirm every model the fixture populated shows up on the clone with
   a non-zero count.
3. `ruff check` on the new fixture + any `demo.py` changes.
4. If `demo.py` changed, run `larpmanager/tests/unit/test_demo_clone.py` to
   make sure the generic clone graph still works for other demo types.
