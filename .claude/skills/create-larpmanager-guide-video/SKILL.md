---
name: create-larpmanager-guide-video
description: Use when creating, re-recording or fixing the videos embedded in the LarpManager Guides (larpmanager.com/guides/). Covers writing Playwright storyboards, rendering with music and text overlays, reviewing the output, and the pitfalls of recording this app.
---

# Creating LarpManager Guide Videos

## What a Guide Video Is

Each guide on larpmanager.com embeds one YouTube video, set through the `LarpManagerGuide.video_id` field: the guide page embeds it at the start, and the guides list plays it in a popup. It shows a real browser completing the guide on a test database, with text overlays and music, and no voice.

Target: English only, 1080p, 90 to 120 seconds, based on the steps of the guide text. A guide with seven or more steps may reach about 2 minutes.

| Guide | URL | Current YouTube ID |
|---|---|---|
| Character Creation | `/guide/creation/` | `HVRTtRkw8AQ` |
| Character Progression | `/guide/xp/` | `ixpT7TS1VQQ` |
| Setup Campaigns | `/guide/campaign/` | `x5_30USosXo` |
| Writing | `/guide/writing/` | `64KylVvb6Zw` |
| Casting | `/guide/assign/` | `YsFjWztbZOI` |
| Payments | `/guide/payments/` | `2Ir2624xocg` |

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

It takes about 3 minutes and needs `xvfb-run` and `ffmpeg`. Output goes to `.guide_videos/output/<slug>/`:

- `guide.mp4`, the video
- `captions.srt`, for YouTube captions
- `thumbnail.png`
- `description.txt`, with YouTube chapters and the required music credit
- `raw.mkv`, `timeline.json` and `captions.ass`, intermediate files

## Writing a Storyboard

Read the guide text and walk the real UI first. A temporary scout storyboard saving `page.screenshot()` at each page is the quickest way to find what each screen actually does. Delete it afterwards.

```python
TITLE = "Setup Campaigns"

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
3. **In multi-role guides, announce every user switch** with `play_as`, including the opening role. Logging in and out stays off camera. Single-role guides skip `play_as` entirely: no role cards and no corner badge.
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

Payments use the Wire method: no external account is needed, and it takes fake details. With a single active method the payment page opens directly on the transfer details, so there is no gateway choice to show. The way to pay starts from the due-payment banner on the event page.

### What cannot be shown

Set `RICH_TEXT = True` in a storyboard to render the real TinyMCE editor, as `writing_storyboard.py` does, when writing text is part of the guide. Type into it through its iframe, and do not use `fill_tinymce` there. Editor ids can depend on database ids, so match them by prefix.

Without that flag, TinyMCE renders as a raw textarea in test settings, so filled rich text shows as `<p>` HTML. Skip optional rich text, as `xp_storyboard.py` does for ability descriptions. Otherwise use `fill_tinymce` inside `off_camera()` and close its panel by clicking the `a.my_toggle` link, as `create_character` does. Date pickers are filled through `fill_date`, without animation.

`lmConfirm` popups (`data-confirm`) are skipped in test runs, so the "are you sure?" step of Upload and of casting Submit never appears on camera. Do not caption it.

Character fields are under the "Sheet" sidebar entry. "Form" and `/manage/form/` are the registration form.

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
| `get_by_label` finds nothing in forms | `elements/form/label.html` renders `<label>` without `for` | Custom fields: `[id^="id_que_"]`. Labels in order: `label[id^="lbl_id_"]` |
| Strict mode error on a list table | Fixed headers make DataTables clone it | `table.writing_list[id^="writing_list"]` |
| Sidebar link not found | A badge joins the link name, such as "Payments 1" | Match the link with `re.compile(r"^Payments")` |
| Second `iframe` or toggle not found | Plot roles repeat per character, with ids depending on database ids | Match by prefix and use `.nth(index)` |
| White band and clipped page bottom | `#page-wrapper` scrolls inside a full-height `body`, so padding on `body` shrinks the visible page | Padding goes on `#wrapper` |
| Hidden actions flash at a cut | Timeline alignment is only approximate | `CUT_MARGIN_SECONDS` keeps the page still around each cut |
| Chrome suggests earlier values | Form history on repeated field names | `type` sets `autocomplete=off` on the field |

Recording also finds real app bugs: treat an odd result as one until proven otherwise. Field reorder left forms stale for a day, and the organizer View page omitted factions; both were found on camera. If the fix belongs in the app, make it there, add a regression test that fails without it, and tell the user it is an app change.

A run ending in `Terminated`, with no test error, usually means another session ran `clean_test.sh`. Stop the leftover `ffmpeg` and `Xvfb` from your run and record again: the isolated database is recreated by itself.

When a run fails, the last frame of `raw.mkv` shows where the page really was: `ffmpeg -sseof -3 -i raw.mkv -frames:v 1 frame.png`.

If a run fails, `guide.mp4` is still the previous render: check its timestamp before reviewing.

Ruff config skips these files, so lint them with `ruff check --isolated --select F,E,W,I --line-length 120 larpmanager/tests/playwright/guide_videos`.

Diagnose before fixing: confirm a cause on the raw files. For example, compare `raw.mkv` duration with `timeline.json` before blaming dropped frames.

## Publishing

Upload manually, with `description.txt` as the description and `captions.srt` as captions. Uploading is public, so the user does it or explicitly approves it.

A new upload gets a new video ID. Update that guide's `LarpManagerGuide.video_id` in the admin; no migration is needed. Automating uploads needs the YouTube Data API, and unaudited API projects can only upload private videos.
