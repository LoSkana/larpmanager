# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**LarpManager** is a Django-based web application for managing LARP (Live Action Role-Playing) events. It provides comprehensive functionality for event organization, character management, registrations, accounting, and more.

## Development Commands

### Common Development Tasks
- **Run tests**: `pytest`
- **Run specific test**: `pytest larpmanager/tests/specific_test.py`
- **Database migrations**: `python manage.py migrate`
- **Create migrations**: `python manage.py makemigrations`
- **Load test fixtures**: `python manage.py reset`
- **Create superuser**: `python manage.py createsuperuser`
- **Run automation tasks**: `python manage.py automate`
- **Lint code**: `ruff check`
- **Format code**: `ruff format`
- **Translation updates**: `./scripts/translate.sh`
- **Record playwright tests**: `./scripts/record-test.sh`
- **Update test dump**: `python manage.py dump_test`

### Frontend Development
- **Install frontend dependencies**: `cd larpmanager/static && npm install`
- **Frontend dependencies are in**: `larpmanager/static/package.json`

### Docker Development
- **Build and run**: `docker compose up --build`
- **Create superuser in container**: `docker exec -it larpmanager python manage.py createsuperuser`
- **Deploy updates**: `docker exec -it larpmanager scripts/deploy.sh`

## Architecture Overview

### Django App Structure
- **Main Django project**: `main/` - Contains settings, URLs, WSGI/ASGI configuration
- **Core app**: `larpmanager/` - Contains all models, views, and business logic
- **Settings structure**: `main/settings/` with environment-specific configs (dev, prod, test, ci)

### Key Model Categories
- **Organizations & Events**: Association, Event, Run management
- **User Management**: Custom Member model, character creation and management
- **Registration System**: Ticket tiers, registration questions, payments
- **Accounting**: Invoice generation, payment tracking, balance management
- **Writing System**: Character backgrounds, story elements
- **Access Control**: Feature-based permissions, role management
- **Inventory**: Item tracking and assignment system

### Core Features Architecture
- **Feature System**: Modular feature flags with `Feature`, `AssocPermission`, `EventPermission` models
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
- **Git LFS**: Required for handling test fixtures (`git lfs pull`)
- **Branch naming**: `prefix/feature-name` (hotfix, fix, feature, refactor, locale)
- **Translation workflow**: DeepL API integration requires `DEEPL_API_KEY` in dev settings

### Permission System
- **Feature-based**: Features control availability of functionality
- **Role-based**: Organization and event-level permissions
- **URL access**: Middleware handles URL-based access control
- **API tokens**: Token-based authentication for external integrations
