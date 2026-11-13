---
name: create-larpmanager-guide-video
description: Use when creating, re-recording or fixing the videos embedded in the LarpManager Guides (larpmanager.com/guides/). Covers writing Playwright storyboards, rendering with music and text overlays, reviewing the output, writing the text and admin entry of a new guide, and the pitfalls of recording this app.
---

# Creating LarpManager Guide Videos

## What a Guide Video Is

Each guide on larpmanager.com embeds one YouTube video, set through the `LarpManagerGuide.video_id` field: the guide page embeds it at the start, and the guides list plays it in a popup. It shows a real browser completing the guide on a test database, with text overlays and music, and no voice.

Target: English only, 1080p, 90 to 120 seconds, based on the steps of the guide text. A guide with seven or more steps may reach about 2 minutes.

| Guide | URL | Current YouTube ID |
|---|---|---|
| Character creation | `/guide/creation/` | `HVRTtRkw8AQ` |
| Character progression | `/guide/xp/` | `ixpT7TS1VQQ` |
| Campaigns | `/guide/campaign/` | `x5_30USosXo` |
| Character fields, factions and plots | `/guide/writing/` | `64KylVvb6Zw` |
| Casting | `/guide/assign/` | `YsFjWztbZOI` |
| Payments | `/guide/payments/` | `2Ir2624xocg` |
| Your first event | `/guide/first/` | Not uploaded yet |
| Tickets and registration form | `/guide/tickets/` | Not uploaded yet |
| Managing your event | `/guide/manage/` | Not uploaded yet |
| Staff and roles | `/guide/roles/` | Not uploaded yet |
| Membership | `/guide/membership/` | Not uploaded yet |
| Event accounting | `/guide/accounting/` | Not uploaded yet |
| Secret links, discounts and waiting list | `/guide/advanced-registration/` | Not uploaded yet |
| Payment plans and deadlines | `/guide/payment-plans/` | Not uploaded yet |

Web fetch tools drop the iframes when converting pages to markdown: use `curl` and grep the raw HTML to check for videos.

## Files

All in `larpmanager/tests/playwright/guide_videos/`:

- `director.py`: paced browser actions, screen capture, caption timeline
- `conftest.py`: `director` fixture, full-screen Chromium on a virtual display
- `compose.py`: captions, intro, recap and outro cards, chapters, music, final render
- `helpers.py`: steps shared by storyboards, such as `create_event`, `register`, `create_character`, `open_menu`
- `<slug>_storyboard.py`: one per video, with `campaign_storyboard.py` and `xp_storyboard.py` as references

The folder must stay under `tests/playwright/`, because `conftest.py` reloads fixtures only for that path. The `_storyboard.py` suffix keeps files out of normal test runs.

Renders and music go to `.guide_videos/`, which is gitignored. Never commit audio.

## Before Recording

Other sessions may be working in the same checkout. Run `ListAgents`, then `git status` and `git reflog -5`.

- Recording needs a branch other than `main`: test database setup refuses to run there.
- If another session is active, work in a git worktree. Do not switch branches in the shared checkout.
- In a worktree, symlink `larpmanager/static/node_modules` from the main checkout, and set `VENV_PYTHON` to the main checkout's `.venv/bin/python`.
- **Do not run `./scripts/clean_test.sh` while anyone else may be testing.** It kills every pytest and playwright process on the machine and drops all `test_%` databases. Ask the user first.

`guide_video.sh` already isolates its database (`test_guide_videos_vid`), through `POSTGRES_DB=guide_videos` and `PYTEST_XDIST_WORKER=vid`. If you run pytest by hand, set both.

## Rendering

```bash
./scripts/guide_video.sh campaign
```

It takes about 3 minutes and needs `xvfb-run` and `ffmpeg`. Run videos one at a time, because they share a database and the capture needs the CPU. To re-render all of them, loop over the slugs in a single background command, and keep a copy of each `guide.mp4` to compare durations. Output goes to `.guide_videos/output/<slug>/`:

- `guide.mp4`, the video
- `captions.srt`, for YouTube captions
- `thumbnail.png`
- `description.txt`, with YouTube chapters and the required music credit
- `raw.mkv`, `timeline.json` and `captions.ass`, intermediate files

## Writing a Storyboard

Read the guide text and walk the real UI first. A temporary scout storyboard saving `page.screenshot()` at each page is the quickest way to find what each screen actually does. Delete it afterwards.

```python
TITLE = "Campaigns"

def test_campaign_video(director):
    page = director.page
    prepare_data()
    login_orga(page, director.base_url)
    director.goto("/manage/events")
    director.start()

    director.play_as(ORGANIZER)
    director.step("Step 1: create the first event")
    director.say("Start from a regular event, no special settings needed")
    ...
    director.stop()
```

| Call | Use for |
|---|---|
| `step(text)` | Large step heading, shown alone for 2.2s |
| `say(text)` | Caption, kept until the next one |
| `click(target)` | Ordinary clicks: links, tabs, sidebar |
| `confirm(target)` | **Every** Confirm, Continue or submit: amber highlight, pause, then click |
| `check(target)` | Checkboxes |
| `type(target, text)` | Text fields, one key at a time |
| `fill(target, text)` | Fields already demonstrated earlier in the video, filled at once |
| `select(target, value)` | Native `<select>` fields |
| `upload(target, path)` | File inputs, as if picked from the file dialog |
| `drag(source, target)` | Drag a handle onto a row, such as `td.reorder-handle`, with the cursor following |
| `spotlight(target, seconds)` | Highlight a result without clicking |
| `play_as(role, prepare)` | Multi-role guides only: full-screen role card and corner badge |
| `off_camera()` | Context manager removing actions from the final video. The current caption resumes afterwards |
| `hold(seconds)` | Let the viewer read |
| `goto(path)` | Only before `start()` or inside `off_camera()` / `prepare` |

A module-level `PACE` sets the speed of cursor moves, clicks, step headings and role cards. It defaults to 1.0; `xp_storyboard.py` uses 0.65 to fit seven steps. `hold` and `spotlight` are not scaled. To shorten a video, first use `fill` for repeated details, then lower `PACE`.

### Rules

1. **Never `goto` on camera.** Viewers see an unexplained jump, and they need to learn the way there. Use the sidebar (`open_menu`) or the link a user would click.
2. **Follow where the app lands.** Check each redirect before adding navigation. Registering lands on the event page; enabling Character creation opens its settings by itself. Clicking on from there is smoother than navigating back.
3. **In multi-role guides, announce every user switch** with `play_as`, including the opening role. Logging in and out stays off camera. `play_as` holds the last screen for 2 seconds before every switch, so never add a `hold` right before it. Single-role guides skip `play_as` entirely: no role cards and no corner badge.
4. **Set the caption before the action it describes**, including before a navigation click. Otherwise the old caption lingers on the new page.
5. **End with proof.** Assert the result with `expect` and `spotlight` it, so a run fails if the guide stops being true.
6. **Keep captions short and in sentence case.** One idea, plain ASCII, read within the time on screen.
7. **Never edit the event slug.** Keep the value computed by the form: `create_event` returns it for later paths.
8. **Explain what looks missing.** If the UI hides something a viewer expects, say why in a caption. Players only see abilities they can afford, so an ability costing more than the available XP is hidden even with its prerequisites met.
9. **Let results sit.** After creating something, wait for the list to show it and `hold` so the viewer can see it.
10. **Close popups on camera** instead of letting them dim the page. Intro tours never appear: the app skips them under pytest.

### Demo data

Replace labels that would look like test data in a `prepare_data()` function run before login: organization name, event names, player name. `Membership.compiled = True` for the player avoids the profile warning and redirect. Use fictional data only, never production.

Data that is not the point of the guide can be created through the ORM, either between two steps or inside a `play_as` `prepare`. `assign_storyboard.py` does this for characters and for the other players with their preferences. Check `larpmanager/fixtures/demos/` first: it holds working examples for most features. Design that data so results are deterministic, then assert them.

Deleting the "Test Larp" event makes the next one a true first event. That form hides the status and registration fields, and opens registrations automatically. Only the later events show those radios.

`first_storyboard.py` starts with no organization at all. `/debug` off camera opens the LarpManager domain, and after the creation form `after_login` sets `debug_slug` and lands on the new `/manage/`, so no manual jump is needed. Its `prepare_organizer` removes the roles of the organizer and `prepare_landing` copies the texts, stats and demo cards of production, because the test database has none and the home page would show an empty hero and "0+" counters. Reuse them for any other video opening on the public pages.

A new organization is in Lite Mode: features cannot be activated, and the sidebar shows only `LITE_PERMISSIONS`. The activation checklist has seven steps with the LarpManager skin, and activating advanced mode needs all of them. The Lite Mode banner (`#lite-mode`) links to the checklist, but it only appears once an event exists. The membership of a new organization has `compiled=False`, so update it after the creation form or registering redirects to the profile. Payment details also need removing after that form, once the association exists.

Uploaded files must look real: `membership_storyboard.py` draws a signed request and a fictional ID card with Pillow into `.guide_videos/`. Saving events, runs and tickets with `.save()` instead of `.update()` keeps cached titles and prices in sync.

Payments use the Wire method: no external account is needed, and it takes fake details. With a single active method the payment page opens directly on the transfer details, so there is no gateway choice to show. The way to pay starts from the due-payment banner on the event page.

### What cannot be shown

Set `RICH_TEXT = True` in a storyboard to render the real TinyMCE editor, as `writing_storyboard.py` does, when writing text is part of the guide. Type into it through its iframe, and do not use `fill_tinymce` there. Editor ids can depend on database ids, so match them by prefix.

Without that flag, TinyMCE renders as a raw textarea in test settings, so filled rich text shows as `<p>` HTML. Skip optional rich text, as `xp_storyboard.py` does for ability descriptions. Otherwise use `fill_tinymce` inside `off_camera()` and close its panel by clicking the `a.my_toggle` link, as `create_character` does. Date pickers are filled through `fill_date`, without animation.

`lmConfirm` popups (`data-confirm`) are skipped in test runs, so the "are you sure?" step of Upload and of casting Submit never appears on camera. Do not caption it.

Character fields are under the "Sheet" sidebar entry. "Form" and `/manage/form/` are the registration form.

The "Go" links of the checklist for event pages (tickets, form, characters, assignment) use `go_redirect_run`, which in dev and test always redirects to `/`. Only "Event creation", "Payment methods" and "First registration" work on camera: use the top bar pills and the sidebar for the others. Those links also go through `redr`, which lists events of every organization of the user, so a leftover role shows a "Please choose" page.

The slug field is collapsed behind a preview. `#slug` still holds the computed value, so reading it works, but it is hidden: spotlight `.slug_pre`, and use `fill_slug` only if a test must change it.

Status and registration radios are collapsed in the Event page behind "Show other options" (`.sl-show`), while the dashboard pencils (`quick-development/`, `quick-registration/`) open modals listing every option. Activating a feature that has settings lands on its configuration section, already open: clicking that section again is not needed. A second session adds a second event pill in the top bar, so match the pill with `exact=True`.

Links on the "Feature activated" page open a new tab, which the script does not follow: reach settings through the sidebar. The new tab also triggers the "Other users are editing" warning.

Some checkboxes, such as a field's "Editable" statuses, are covered by their label. Click the label with `click`: `check` waits forever on them.

Use what the app points to. Proposed characters show "1 characters to approve" on the event dashboard and a badge on the sidebar link, so `open_menu` cannot match that link by exact name. Spotlight the notice, then click the link with a regex name.

For forms with extra fields, use `open_character_form`, then the fields, then `submit_character`. `create_character` covers the default fields only.

Writing lists offer more than edit: row icons `.fa-book-open` (View) and `.fa-file-alt` (Versions), and links that add a column: `a.table_toggle` for built-in ones such as Characters, `a.load_que` for custom fields.

Selectors and helpers can usually be taken from `larpmanager/tests/playwright/*_test.py`. Look for a test of the same feature first.

## Music

Use "Inspired" by Kevin MacLeod, downloaded by the script at build time. It is free under CC BY 4.0 with credit in the video description, including for monetized videos. The credit in `description.txt` declares the trim and fade.

Tracks must be human-composed, not AI-generated. Before using another track, confirm its license on the source site. Pixabay was rejected because human authorship could not be confirmed per track and it warns of Content ID claims. If YouTube flags a MacLeod track, add the credit and dispute the claim.

## Recap Card and Chapters

`compose.py` builds both from the `step()` headings, so no storyboard change is needed and they stay in sync with the steps. Changing them needs only a re-compose from `raw.mkv`, not a new recording:

```bash
.venv/bin/python larpmanager/tests/playwright/guide_videos/compose.py .guide_videos/output/<slug> .guide_videos/music/Inspired.mp3 larpmanager/static/lm_logo.png
```

- The recap card follows the title card, lists the steps as "In this guide", and adds 2s plus 0.5s per step. Count it in the 90 to 120 second target.
- Step headings lose their "Step N:" prefix on the card and in chapters, so write them to read well alone.
- YouTube ignores all chapters unless the first is at 0:00, there are at least 3, and each lasts 10 seconds or more. So the first step is placed at 0:00, and a step starting under `MIN_CHAPTER_SECONDS` after the previous chapter is merged into it. Such a step is on the card but not in the chapters.
- Do not run a compose during a recording: the encoder takes the CPU and can drop capture frames.

## Reviewing the Output

A passing run does not prove a good video. Always extract frames and read them before reporting:

```bash
ffmpeg -y -v error -ss 40 -t 6 -i .guide_videos/output/<slug>/guide.mp4 \
  -vf "fps=2,scale=480:-1,tile=4x3" -frames:v 1 <scratchpad>/sheet.png
```

Use the timings in `captions.ass` to choose ranges. A sheet covering the whole video at `fps=1/5` shows overall flow; use `fps=2` around each transition.

Check that:

- The text on screen matches what the page shows
- The cursor and amber highlight appear on every Confirm, **including inside modals**
- No caption covers the button being clicked
- Results are actually in view: lists can sit below the fold, so scroll to them or `spotlight` them
- No raw `<p>` HTML is visible, and captions stay on through Confirm clicks
- No Chrome autofill suggestions appear on typed fields
- In multi-role guides, every user switch has a card and the badge shows the right role
- There are no unexplained page jumps, leftover dialogs, browser bars or password bubbles
- The intro, recap card, outro and final proof all render
- The recap lists every step without clipping, and `description.txt` has at least 3 chapters

If the run fails, `guide.mp4` is still the previous render, so check its timestamp before reviewing frames. Say what you checked and how. You can't hear audio or feel pacing, so ask the user to watch every new render. Reporting "done" needs their review.

## Known Pitfalls

Already handled in the code. Keep these fixes when changing it.

| Symptom | Cause | Handling |
|---|---|---|
| Captions run late by a fixed amount | ffmpeg buffers, so the first bytes appear seconds after the first frame | `align_to_recording` measures the offset from raw length |
| Cursor and effects missing in modals | `#lm-modal` is a `<dialog>` in the top layer, above any z-index | Overlays use the Popover API, and the cursor re-enters the top layer when a dialog opens |
| Click effect never seen | Navigation destroys the page before it plays | Pause before clicking |
| Browser bar visible | Kiosk mode only applies to the default window | `launch_persistent_context` |
| "Save password?" bubble | Chrome password manager | `BROWSER_PREFERENCES` in the profile |
| Window larger than the screen | `--window-size` is scaled by the UI factor | Divide the size by `UI_SCALE` |
| Caption covers a low button | Button sits at the bottom of the page | Extra page padding, and targets below `CAPTION_SAFE_AREA` get centered |
| `Target has no visible box` right after a modal save | The list reloads after the modal closes, replacing the rows under an existing locator | Wait for the row just saved before touching any other row |
| Payment fields already masked before typing | Saved details live in a `main/payment_settings/` file that outlives the database reset | The storyboard removes the file of its worker before login |
| ffmpeg survives a failed run | Test fails before `stop()` | `abort()` in fixture teardown |
| `get_by_label` finds nothing in forms | `elements/form/label.html` renders `<label>` without `for` | Custom fields: `input[id^="id_que_"]`, or the input of `tr` with the question name, because the bare prefix also matches the row. Labels in order: `label[id^="lbl_id_"]` |
| Strict mode error on a list table | Fixed headers make DataTables clone it | `table.writing_list[id^="writing_list"]` |
| Sidebar link not found | A badge joins the link name, such as "Payments 1" | Match the link with `re.compile(r"^Payments")` |
| Second `iframe` or toggle not found | Plot roles repeat per character, with ids depending on database ids | Match by prefix and use `.nth(index)` |
| White band and clipped page bottom | `#page-wrapper` scrolls inside a full-height `body`, so padding on `body` shrinks the visible page | Padding goes on `#wrapper` |
| Hidden actions flash at a cut | Timeline alignment is only approximate | `CUT_MARGIN_SECONDS` keeps the page still around each cut |
| Chrome suggests earlier values | Form history on repeated field names | `type` sets `autocomplete=off` on the field |
| Red underlines on names and fake data | Chrome spellcheck | `enable_spellchecking` off in `BROWSER_PREFERENCES`, and `spellcheck=false` set by `type` and `fill` |
| `spotlight` times out on `#page-wrapper` | Landing pages have no such element | `_box_within_content` returns the plain box there |
| Spotlight on a sidebar link is a sliver at the content edge | Boxes are clamped to the content area | Targets entirely inside the sidebar skip the clamp |
| Clicks stop reaching the page after a new user logs in | Chrome password leak detection opens a native bubble, invisible in screenshots, that swallows input ("banana" is a breached password) | `password_manager_leak_detection` off in `BROWSER_PREFERENCES` |
| Strict mode error on `.run-card` | The calendar renders the list twice, for `.only_v22` and `.no_v22` | `.only_v22 .run-card` |

Recording also finds real app bugs: treat an odd result as one until proven otherwise. Field reorder left forms stale for a day, and the organizer View page omitted factions; both were found on camera. If the fix belongs in the app, make it there, add a regression test that fails without it, and tell the user it is an app change.

A run ending in `Terminated`, with no test error, usually means another session ran `clean_test.sh`. Stop the leftover `ffmpeg` and `Xvfb` from your run and record again: the isolated database is recreated by itself.

When a run fails, the last frame of `raw.mkv` shows where the page really was: `ffmpeg -sseof -3 -i raw.mkv -frames:v 1 frame.png`.

If a run fails, `guide.mp4` is still the previous render: check its timestamp before reviewing.

Ruff config skips these files, so lint them with `ruff check --isolated --select F,E,W,I --line-length 120 larpmanager/tests/playwright/guide_videos`.

Diagnose before fixing: confirm a cause on the raw files. For example, compare `raw.mkv` duration with `timeline.json` before blaming dropped frames.

## Publishing

Upload manually, with `description.txt` as the description and `captions.srt` as captions. Uploading is public, so the user does it or explicitly approves it.

Every guide is an entry of `larpmanager/fixtures/guide.yaml`, loaded by `import_features` on every deploy (matched by `slug`), so the fixture is the source of truth: edits made in the production admin to its fields are overwritten. For each video, new or re-recorded, add or update its entry with the fields `slug`, `number`, `group`, `title`, `description`, `keywords`, `icon`, `published` and `text`:

- `slug` is the public URL `/guide/<slug>/`: never rename it once published.
- `description` is the short description, one sentence starting with "How to", shown in the guides list.
- `keywords` is a comma separated list of 4-8 terms.
- `icon` is only the Font Awesome name, such as `calculator`: the template adds `fa-solid fa-`.
- `text` is the full description, as a YAML `|` block: an intro paragraph, `<hr>`, one `<h4>Step N &ndash; Title</h4>` plus a short paragraph per storyboard step, `<hr>`, then `<p><strong>Related resources</strong></p>` and a `<ul>` of `<li>Topic with <strong>key words</strong> (<a href="...">read here</a>)</li>`. Plain ASCII with HTML entities. Keep each step true to the final video, and keep one `<h4>` per `step()` of the storyboard.
- Every management page named in the text is a scoped link, as in the tutorials: `<a href="https://larpmanager.com/redirect/event/manage/<path>/" target="_blank" rel="noopener"><strong>Event &gt; <Sidebar label></strong></a>` for event pages, `https://larpmanager.com/redirect/manage/<path>/` and `Organization &gt; <Sidebar label>` for organization pages, and `Event &gt; Configuration &gt; <Section>` (`.../config/<section>/`) for a configuration section. Never write a bare page name ("open Tickets", "in the Payments page", "the event Features"), and never point a page name to a tutorial: link tutorials on feature names or in Related resources. Labels and paths follow the link rules of the `write-larpmanager-tutorial` skill (sidebar label = `name` in `event_permission.yaml` / `association_permission.yaml`, path from `reverse()` of its `slug`). Pages players see (event menu, home page sidebar) and buttons or fields inside a page are not links.
- Related resources must link both the tutorials (`/tutorials/<slug>/`) and the other guides (`/guide/<slug>/`, singular: `/guides/<slug>/` is a 404). Every guide must be linked by at least one other guide. Check each link with `curl` before finishing.
- `number` sorts the guides page, and `group` is a heading on it: guides sharing a group are listed together, groups in order of first appearance. The groups are Getting started, Registrations, Accounting, Campaign, One-shot and Organization; renumber the following entries when inserting a guide.
- `video_id` and `photo` are not in the fixture, and deploys never touch them: after the upload, the user sets the video ID (and the thumbnail as photo) in the admin. A re-recorded video gets a new video ID.

Run `python manage.py import_features` and open `/guides/` and the guide page to check them.

Automating uploads needs the YouTube Data API, and unaudited API projects can only upload private videos.
