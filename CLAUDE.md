# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**LarpManager** is a Django-based web application for managing LARP (Live Action Role-Playing) events. It provides comprehensive functionality for event organization, character management, registrations, accounting, and more.

## Documentation

- **[Features and Permissions Guide](docs/01-features-and-permissions.md)** - Comprehensive guide for creating features, views, and permissions
- **[Roles and Context Guide](docs/02-roles-and-context.md)** - How to structure views with context and understand role-based permissions
- **[Configuration System Guide](docs/03-configuration-system.md)** - How to add customizable settings without modifying models
- **[Localization Guide](docs/04-localization.md)** - How to write translatable code and manage translations
- **[Playwright Testing Guide](docs/05-playwright-testing.md)** - How to write and run end-to-end tests
- **[Feature Descriptions](docs/06-feature-descriptions.md)** - Complete reference of all available features
- **[Test Database Schema Versioning](docs/07-test-database-schema-versioning.md)** - How the automatic schema version detection works
- **[Security Best Practices](docs/08-security-best-practices.md)** - Critical security requirements including UUID usage
- **[README.md](README.md)** - Installation, deployment, and contribution guidelines

## Code Conventions

- **Never name a variable `_`** - use a descriptive name or a more specific throwaway like `_unused`.
- **Never use non-ascii characters** - if a symbol is needed, use a font-awesone icon.
- **Never put css style inline** - always put the css in lm.css.
- **One migration for branch** - in case there is more changes to be done to the model, first make the new migration, execute it to update db, the join the code of the new migration with the other one, and remove the newer
- **Concise pydocs** - Use concise pydocs and comments, that shouldn't talk about the current change, only of the function overall behaviour.
## Package Management

The project uses **uv** for fast and reliable Python package management. All dependencies are defined in `pyproject.toml`.

### Installing uv
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Installing dependencies
```bash
# System-wide (for Docker and CI)
uv pip install --system -r pyproject.toml

# In a virtual environment
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv pip install -r pyproject.toml
```

### Upgrading dependencies
Use the `./scripts/pip_upgrade.sh` script which has been updated for uv:
```bash
./scripts/pip_upgrade.sh
```

## Virtual Environment

The virtual environment is located at `.venv` in the project working directory. Always use it directly for Python and ruff commands:
```bash
.venv/bin/ruff check <file>
.venv/bin/ruff format <file>
.venv/bin/python manage.py <command>
```
Do not prefix with `source .venv/bin/activate &&`, invoke the venv binaries directly (e.g. `.venv/bin/ruff`, `.venv/bin/python`).
For pytest and scripts, use `source <venv>/bin/activate` or `./scripts/test.sh`.

## Development Commands

### Common Development Tasks
- **Run all tests**: `./scripts/test.sh [workers]` (default: 6 workers)
- **Run specific test**: `pytest larpmanager/tests/specific_test.py`
- **If tests fail to run (DB/schema errors, stale test DB)**: run `./scripts/clean_test.sh [workers]` first — it regenerates the test dump via `manage.py dump_test` if its schema version is stale, then drops/recreates the test databases (same cleanup `./scripts/test.sh` does). Run it once, then retry the test.
- **Run unit tests only**: `./scripts/test_unit.sh`
- **Run playwright tests only**: `./scripts/test_playwright.sh`
- **Create migrations**: `python manage.py makemigrations`
- **Apply migrations**: `python manage.py migrate`
- **Load test fixtures**: `python manage.py reset` (creates test org with users: `admin`, `orga@test.it`, `user@test.it` - password: `banana`) - automatically runs makemigrations and migrate
- **Create superuser**: `python manage.py createsuperuser`
- **Run automation tasks**: `python manage.py automate` (should be scheduled daily, handles advanced features)
- **Lint code**: `ruff check`
- **Format code**: `ruff format`
- **Translation updates**: `./scripts/translate.sh` (requires `DEEPL_API_KEY` in dev settings)
- **Record playwright tests**: `./scripts/record-test.sh`
- **Update test dump**: `python manage.py dump_test` (required after model/fixture changes) - automatically runs makemigrations, migrate, and reset; auto-adds schema version marker

### Feature Management
- **Export features to fixtures**: `python manage.py export_features` (run before pushing new features)
- **Import features from fixtures**: `python manage.py import_features` (automatically run during deploy)

### Frontend Development
- **Install frontend dependencies**: `cd larpmanager/static && npm install`
- **Frontend dependencies are in**: `larpmanager/static/package.json`

### Docker Development
- **Build and run**: `docker compose up --build`
- **Create superuser in container**: `docker exec -it larpmanager python manage.py createsuperuser`
- **Deploy updates**: `docker exec -it larpmanager scripts/deploy.sh` (graceful restart with migrations)
- **Build CI image**: `./scripts/build_ci_image.sh` (for updating CI Docker image)
- **Build and push CI image**: `./scripts/build_ci_image.sh --push` (requires GHCR authentication)

## Architecture Overview

### Django App Structure
- **Main Django project**: `main/` - Contains settings, URLs, WSGI/ASGI configuration
- **Core app**: `larpmanager/` - Contains all models, views, and business logic
- **Settings structure**: `main/settings/` with environment-specific configs (dev, prod, test, ci)

### Key Model Categories
Models are organized in `larpmanager/models/` by domain:
- **Organizations & Events**: `association.py`, `event.py` - Association, Event, Run management
- **User Management**: `member.py` - Custom Member model, character creation and management
- **Registration System**: `registration.py` - Ticket tiers, registration questions, payments
- **Accounting**: `accounting.py` - Invoice generation, payment tracking, balance management
- **Writing System**: `writing.py` - Character backgrounds, story elements
- **Access Control**: `access.py` - Feature-based permissions, role management
- **Forms & Questions**: `form.py` - Dynamic form system for registration/applications
- **Other domains**: `casting.py`, `experience.py`, `miscellanea.py`
- **IMPORTANT**: Only add new fields to models if they are used by EVERY instance. Otherwise use `EventConfig`, `RunConfig`, or `AssocConfig`
- **SECURITY**: Models referenced in URLs or frontend must inherit from `UuidMixin` (see [Security Best Practices](docs/08-security-best-practices.md))

### Core Features Architecture
- **Feature System**: Modular feature flags system (see [Features and Permissions Guide](docs/01-features-and-permissions.md))
  - `Feature`, `AssociationPermission`, `EventPermission` models control functionality
  - `overall=True` for organization-wide, `overall=False` for event-specific
  - View naming: `orga_*` (event-specific), `exe_*` (organization-wide)
  - Always run `python manage.py export_features` after creating/modifying features
- **Multi-tenancy**: Organization-based with URL slugs (`SLUG_ASSOC` setting)
- **Caching**: Redis-based caching for performance
- **Internationalization**: Full i18n support with DeepL API integration
- **Payment Processing**: PayPal, Stripe, and Redsys gateway integrations

### Frontend Architecture
- **Template system**: Django templates with TinyMCE integration
- **Static files**: Managed with django-compressor
- **JavaScript libraries**: PayPal JS SDK, TinyMCE, table2csv, driver.js
- **Responsive design**: Bootstrap-based UI

### Testing Strategy
- **Test framework**: pytest with django-pytest plugin; always run only one test at a time.
- **E2E testing**: Playwright for browser automation
- **Test markers**: `@pytest.mark.e2e`, `@pytest.mark.slow`, `@pytest.mark.django_db_reset_sequences`
- **Test location**: `larpmanager/tests/` directory
- **Debugging failures**: Run with `RECORD=1`; on failure, screenshot and HTML are saved to `test_screenshots/{timestamp}_{testname}.{png,html}`. Always read the saved HTML to understand what the page actually showed before attempting to fix a failing test.

### Key Configuration Files
- **Django settings**: Environment-specific files in `main/settings/`
- **Database**: PostgreSQL with connection pooling
- **Cache**: Redis configuration
- **Static files**: Compression and asset management
- **Translation**: Babel configuration for i18n

### Deployment Architecture
- **Production**: Gunicorn + Nginx
- **Containerized**: Docker with PostgreSQL and Redis services
- **Background tasks**: django4-background-tasks for async processing
- **File storage**: Local media files with proper permissions

### Development Workflow
- **Pre-commit hooks**: Installed via `pre-commit install`
  - Includes: ruff, djlint, translate, gitleaks, prevent-main-commit
- **Git LFS**: Required for test fixtures (`git lfs install && git lfs pull`)
- **Branch naming**: `prefix/feature-name`
  - Prefixes: `hotfix`, `fix`, `feature`, `refactor`, `locale`
- **Translations**: DeepL API integration requires `DEEPL_API_KEY` in dev settings
  - Run `./scripts/translate.sh` to update translations
- **Upgrade script**: `./scripts/upgrade.sh`
  - Merges main, runs migrations, translations, pushes branch
  - **Never run on main branch**
- **Pull requests**: Include only minimal changes necessary
  - Avoid refactoring unless approved beforehand
  - Keep commits focused and atomic

### Permission System
- **Feature-based**: Features control availability of functionality (see [Features Guide](docs/01-features-and-permissions.md))
- **Role-based**: Organization and event-level roles with assigned permissions
- **URL access**: Middleware handles URL-based access control (`larpmanager/middleware/`)
- **API tokens**: Token-based authentication for external integrations
- **Sidebar links**:
  - `AssociationPermission` for organization dashboard
  - `EventPermission` for event dashboard
  - Both link to views via `slug` field

## Contributing Workflow

### General Workflow

1. **Create branch**: `git checkout -b prefix/feature-name`
   - Prefixes: `feature`, `fix`, `hotfix`, `refactor`, `locale`

2. **Develop your changes**:
   - For new features with UI, see [Features and Permissions Guide](docs/01-features-and-permissions.md)
   - Follow naming conventions: `orga_*` for event views, `exe_*` for organization views
   - Only add model fields if used by EVERY instance (otherwise use Config models)
   - **CRITICAL**: Follow [Security Best Practices](docs/08-security-best-practices.md) - especially UUID usage

3. **Update fixtures if needed**:
   - Models/fixtures changed: `python manage.py dump_test`
   - Features/permissions changed: `python manage.py export_features`

4. **Write tests**:
   - New functionality requires playwright tests in `larpmanager/tests/`
   - Run tests: `pytest`

5. **Before pushing**:
   - Run `./scripts/upgrade.sh` (merges main, migrations, translations, push)
   - Ensure all tests pass

6. **Create pull request** with minimal, focused changes

### Feature Development Quick Reference

For adding new features with views and permissions, follow the [Features and Permissions Guide](docs/01-features-and-permissions.md). Summary:

1. Determine scope: organization-wide (`overall=True`) or event-specific (`overall=False`)
2. Create `Feature` object with appropriate `overall` setting
3. Create views: `exe_*` for organization, `orga_*` for events
4. Create permissions: `AssociationPermission` and/or `EventPermission`
5. Run `python manage.py export_features`
6. Test thoroughly

## Environment Setup

### Development Setup
1. **Install Python 3.12** or higher (Ubuntu 24.04 LTS recommended)
2. Copy `main/settings/dev_sample.py` to `main/settings/dev.py`
3. Configure database settings in `DATABASES`
4. Set `SLUG_ASSOC` to organization slug (default: `test`)
5. Add `DEEPL_API_KEY` for translation features (get free API key from DeepL)
6. Run `python manage.py reset` to set up database and load test fixtures
7. Install pre-commit hooks: `pre-commit install`
8. Install Git LFS: `git lfs install && git lfs pull`

### Production Setup
1. Copy `main/settings/prod_sample.py` to `main/settings/prod.py`
2. Configure production settings (database, cache, secret key, etc.)
3. Set up Google SSO following django-allauth guide
4. Configure PostgreSQL and Redis
5. Set up daily automation: `docker exec -it larpmanager python manage.py automate`


### LarpManager CSS — where to put what

When adding a rule, drop it in the file whose scope matches. If a selector fits
two files, prefer the more specific/feature file over `00-base`. Add new rules
under the matching section-comment banner inside the file.

| File | Put here | Do NOT put here |
|------|----------|-----------------|
| `00-base.css` | Page-agnostic primitives: single-purpose utility classes (`.hide`, `.show`, `.inline`, `.centerized`), bare HTML element defaults/resets (`table`, `form`, `select`, `button`, `label`, `ul/ol`), low-level text/color helpers (`.helptext`, `.errorlist`, `.redderized`), and the `body.theme-*` color-skin definitions (Themes section). | Anything component- or feature-specific. |
| `01-forms.css` | Form inputs and their widgets: native `input`/checkbox/radio styling, custom option cards (`.opt-card`, `.reg-checkbox-class`), `#register_form` layout, form errors, reCAPTCHA, Select2 (`.select2-*`), TinyMCE (`.tox-*`), form-control width/responsive rules, `.form_container` layout incl. the `.new_v18` form-table variant. | DataTables controls (→ `03`), table layout (→ `02`). |
| `02-tables.css` | `table`/`th`/`td`/`tr` layout, table-scoped responsive stacking (`.mob`, `.table-responsive`), rules tied to specific tables (inline options editor `.inline-options-table`, `#discount_tbl`). | DataTables-generated markup (→ `03`), non-table layout. |
| `03-datatables.css` | Anything targeting DataTables-generated markup: selectors starting with `.dt-`, `.dtcc-`, `.dataTable`, `.dataTables_wrapper` — library controls, pagination, search/length inputs, column-control dropdowns, export buttons, cell/scrollbar overrides. | Plain HTML tables (→ `02`), the responsive inline-expand caret (→ `09`). |
| `04-popups.css` | Loading spinners/overlays (`#overlay`, `.lds-roller`), toast notifications (`.jq-toast-*`), and any popup/modal/dialog/lightbox (`.popup*`, `dialog`, `#char-finder-popup`, `#excel-edit`, `#imagePopup`) — shells, size variants, backdrops, close buttons. | Manage-side option-edit popup and floating iframe (→ `07`). |
| `05-nav.css` | Navigation-bar styling (`.nav`, `.links a`, `.sheet`) and login/auth forms (`.login`, `.allauth_signin`, `.password_reset`, `.registration_register`). | Page shell/topbar/sidebar (→ `10`-`12`). |
| `06-application.css` | Domain/feature UI for player-facing app: registration status (`.reg_status`), character/profile (`.char_profile`, `#player_relationships`), membership (`.membership_request`), payments (`.satispay-button`, `#paypal-buttons`, `.accounting_record`), feature toggles (`.feature_checkbox`), app-widget misc (`.editable`, `.ajax-toggle`, `.paginate`, `#search`, `.abilities`). | Base layout/theme tokens, generic components, manage-side chrome (→ `07`). |
| `07-dashboard.css` | Organizer/staff manage-side chrome: `#manage`/`.manage` panels, sticky notices, `#wwyltd` quick-action select2, AJAX option-edit popups (`.ajax-option-form-container`), driver.js tour tooltips (`.my-driverjs`), one-time media pages (`.onetime-*`), floating-iframe embedding (`body.floating_iframe`, `#options-iframe`, `.frame-container`), the manage dashboard grid (`.grid`, `.grid-item`, `.copy-link-btn`). | Player-facing feature styling (→ `06`), page shell (→ `10`-`12`). |
| `08-casting.css` | Casting/character-preference assignment UI (`.casting-*`, `.faction-chip`, `.char-card`, drag-rank `.pref-*`) and badge/leaderboard pages (`.page_badges`, `.badge-selector`, `.char-assign-icon`). | Generic character/profile display (→ `06`). |
| `09-widgets.css` | Self-contained interactive widgets: DataTables responsive expand caret (`td.dtr-control::before`), Version 20 interface shell (`.new_v20 ...`, `.reg-confirmed/.reg-pending`), ability selector (`.ability-*`, `.exp-stat-*`), character dual-list transfer (`.char-dual-*`). | Generic layout/typography/base. |
| `10-structure.css` | Page skeleton not owned by one bar: `html`/`body`, `#page-container`, `#page-wrapper`, `#wrapper`, `#staging`, `#header h1`, `#footer.lm`, the `#one/#topbar/#sidebar/#footer .inner` visibility resets, `.only_mobile`, and the `.new_v22` page-wrapper/banner overrides. | Topbar-only rules (→ `11`), sidebar-only rules (→ `12`). |
| `11-topbar.css` | `#topbar` and everything rendered inside it: base topbar layout + `--topbar-height`, mobile topbar table, `#right_bar`, nav dropdowns (`.dropdown*`), the v22 topbar shell (`#topbar.topbar_v22`) and pill/switch widgets (`.tv22-*`). | Sidebar (→ `12`), generic page shell (→ `10`). |
| `12-sidebar.css` | `#sidebar` and everything rendered inside/around it: base sidebar layout, mobile sidebar overlay, `#mobile-bar`, the v22 sidebar shell incl. collapse toggle (`#sidebar-collapse-btn`), sidebar status badges (`.sidebar-status-badge`), context selector, and the v22 mobile bottom bar (`#menu-mobile`). | Topbar (→ `11`), generic page shell (→ `10`). |
| `13-miscellanea.css` | v22 cross-cutting rules not tied to the shell: visibility toggles (`.new_v22 .no_v22`/`.only_v22`), reg-status/`.reg-banner` styling, v22 typography alignment, calendar run-card grid (`.run-card-*`), event-page two-column layout (`.event-*`), payment summary cards (`.payment-summary-*`). | Shell/chrome (→ `10`-`12`). |

- CSS color vars (`--pri-rgb`, `--sec-rgb`, `--ter-rgb`, `--ter-clr`) are defined
  by the `body.theme-*` rules in `00-base.css` and by per-association/event skin
  CSS; `--topbar-height` is defined in `11-topbar.css`. Files consume these vars
  without redefining them.
- Version flags: `.new_v18` → `01`/`11`, `.new_v20` → `09`, `.new_v22`/`.only_v22`/
  `.no_v22` → distributed across `10`-`13` by which shell component the rule
  touches (page skeleton, topbar, sidebar, or cross-cutting).
- Never inline CSS in templates — all styles live here (per CLAUDE.md).
- No non-ASCII characters; use a Font Awesome icon if a symbol is needed.
