# LarpManager CSS — where to put what

`lm.css` was split into ordered, feature-grouped files under this folder. The
build concatenates them **in filename order** (`00-` → `10-`) inside the
`{% compress css %}` block in `elements/structure/css-larpmanager.html`, so the
cascade is identical to the old single file. **Order matters** — later files
override earlier ones. Keep the numeric prefixes and never reorder.

When adding a rule, drop it in the file whose scope matches. If a selector fits
two files, prefer the more specific/feature file over `00-base`. Add new rules
under the matching section-comment banner inside the file.

## File map

| File | Put here | Do NOT put here |
|------|----------|-----------------|
| `00-base.css` | Page-agnostic primitives: single-purpose utility classes (`.hide`, `.show`, `.inline`, `.centerized`), bare HTML element defaults/resets (`table`, `form`, `select`, `button`, `label`, `ul/ol`), low-level text/color helpers (`.helptext`, `.errorlist`, `.redderized`). | Anything component- or feature-specific. |
| `01-forms.css` | Form inputs and their widgets: native `input`/checkbox/radio styling, custom option cards (`.opt-card`, `.reg-checkbox-class`), `#register_form` layout, form errors, reCAPTCHA, Select2 (`.select2-*`), TinyMCE (`.tox-*`), form-control width/responsive rules. | DataTables controls (→ `03`), table layout (→ `02`). |
| `02-tables.css` | `table`/`th`/`td`/`tr` layout, table-scoped responsive stacking (`.mob`, `.table-responsive`), rules tied to specific tables (inline options editor `.inline-options-table`, `#discount_tbl`). | DataTables-generated markup (→ `03`), non-table layout. |
| `03-datatables.css` | Anything targeting DataTables-generated markup: selectors starting with `.dt-`, `.dtcc-`, `.dataTable`, `.dataTables_wrapper` — library controls, pagination, search/length inputs, column-control dropdowns, export buttons, cell/scrollbar overrides. | Plain HTML tables (→ `02`), the responsive inline-expand caret (→ `09`). |
| `04-popups.css` | Loading spinners/overlays (`#overlay`, `.lds-roller`), toast notifications (`.jq-toast-*`), and any popup/modal/dialog/lightbox (`.popup*`, `dialog`, `#char-finder-popup`, `#excel-edit`, `#imagePopup`) — shells, size variants, backdrops, close buttons. | Manage-side option-edit popup and floating iframe (→ `07`). |
| `05-nav.css` | Navigation-bar styling (`.nav`, `.links a`, `.sheet`) and login/auth forms (`.login`, `.allauth_signin`, `.password_reset`, `.registration_register`). | v22 sidebar/topbar (→ `10`). |
| `06-application.css` | Domain/feature UI for player-facing app: registration status (`.reg_status`), character/profile (`.char_profile`, `#player_relationships`), membership (`.membership_request`), payments (`.satispay-button`, `#paypal-buttons`, `.accounting_record`), feature toggles (`.feature_checkbox`), app-widget misc (`.editable`, `.ajax-toggle`, `.paginate`, `#search`, `.abilities`). | Base layout/theme tokens, generic components, manage-side chrome (→ `07`). |
| `07-dashboard.css` | Organizer/staff manage-side chrome: `#manage`/`.manage` panels, sticky notices, `#wwyltd` quick-action select2, AJAX option-edit popups (`.ajax-option-form-container`), driver.js tour tooltips (`.my-driverjs`), one-time media pages (`.onetime-*`), floating-iframe embedding (`body.floating_iframe`, `#options-iframe`, `.frame-container`). | Player-facing feature styling (→ `06`), v22 shell (→ `10`). |
| `08-casting.css` | Casting/character-preference assignment UI (`.casting-*`, `.faction-chip`, `.char-card`, drag-rank `.pref-*`) and badge/leaderboard pages (`.page_badges`, `.badge-selector`, `.char-assign-icon`). | Generic character/profile display (→ `06`). |
| `09-widgets.css` | Self-contained interactive widgets: DataTables responsive expand caret (`td.dtr-control::before`), Version 20 interface shell (`.new_v20 ...`, `.reg-confirmed/.reg-pending`), ability selector (`.ability-*`, `.exp-stat-*`), character dual-list transfer (`.char-dual-*`). | Generic layout/typography/base. |
| `10-v22.css` | Everything gated by the v22 flag (`.new_v22`/`.only_v22`/`.no_v22`): sidebar/topbar/mobile-menu layout, collapse toggle (`#sidebar-collapse-btn`), reg-status badges/banners (`.sidebar-status-badge`, `.reg-banner`), topbar pills (`.tv22-*`), calendar run-card grid (`.run-card-*`), event-page two-column layout (`.event-*`), payment summary cards (`.payment-summary-*`). | Anything not tied to the v22 flag or these components. |

## Shared conventions

- CSS color vars (`--pri-rgb`, `--sec-rgb`, `--ter-rgb`, `--ter-clr`, `--topbar-height`)
  are **used** across files but defined elsewhere (theme/skin), not here.
- Version flags: `.new_v20` → `09`, `.new_v22`/`.only_v22`/`.no_v22` → `10`.
- Never inline CSS in templates — all styles live here (per CLAUDE.md).
- No non-ASCII characters; use a Font Awesome icon if a symbol is needed.