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
- **[README.md](README.md)** - Installation, deployment, and contribution guidelines

## Development Commands

### Common Development Tasks
- **Run tests**: `pytest`
- **Run specific test**: `pytest larpmanager/tests/specific_test.py`
- **Run unit tests only**: `./scripts/test_unit.sh`
- **Run playwright tests only**: `./scripts/test_playwright.sh`
- **Database migrations**: `python manage.py migrate`
- **Create migrations**: `python manage.py makemigrations`
- **Load test fixtures**: `python manage.py reset` (creates test org with users: `admin`, `orga@test.it`, `user@test.it` - password: `banana`)
- **Create superuser**: `python manage.py createsuperuser`
- **Run automation tasks**: `python manage.py automate` (should be scheduled daily, handles advanced features)
- **Lint code**: `ruff check`
- **Format code**: `ruff format`
- **Translation updates**: `./scripts/translate.sh` (requires `DEEPL_API_KEY` in dev settings)
- **Record playwright tests**: `./scripts/record-test.sh`
- **Update test dump**: `python manage.py dump_test` (required after model/fixture changes)

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
- **Test framework**: pytest with django-pytest plugin
- **E2E testing**: Playwright for browser automation
- **Test markers**: `@pytest.mark.e2e`, `@pytest.mark.slow`, `@pytest.mark.django_db_reset_sequences`
- **Test location**: `larpmanager/tests/` directory

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
1. Copy `main/settings/dev_sample.py` to `main/settings/dev.py`
2. Configure database settings in `DATABASES`
3. Set `SLUG_ASSOC` to organization slug (default: `test`)
4. Add `DEEPL_API_KEY` for translation features (get free API key from DeepL)
5. Run `python manage.py reset` to load test fixtures
6. Install pre-commit hooks: `pre-commit install`
7. Install Git LFS: `git lfs install && git lfs pull`

### Production Setup
1. Copy `main/settings/prod_sample.py` to `main/settings/prod.py`
2. Configure production settings (database, cache, secret key, etc.)
3. Set up Google SSO following django-allauth guide
4. Configure PostgreSQL and Redis
5. Set up daily automation: `docker exec -it larpmanager python manage.py automate`
