# Developer Guide: Features and Permissions

This guide explains how to add new features and create views with proper permissions in LarpManager.

**Related guide:** After reading this, see [Roles and Context Guide](02-roles-and-context.md) to learn how to structure views and implement permission checks.

## Table of Contents

1. [Overview](#overview)
2. [The Feature System](#the-feature-system)
3. [Creating Features](#creating-features)
4. [Permission System](#permission-system)
5. [View Naming Conventions](#view-naming-conventions)
6. [Working with Fixtures](#working-with-fixtures)
7. [Step-by-Step Workflow](#step-by-step-workflow)
8. [Examples](#examples)

---

## Overview

LarpManager uses a modular feature system that controls functionality at both **organization** and **event** levels. This system allows administrators to enable/disable specific features for their organization or individual events, providing flexibility in what functionality is available.

### Important: Avoid Feature Proliferation

**Before creating a new feature, consider if you can extend an existing one instead.**

Features should be created only when introducing genuinely new functionality that is independent from existing features. In most cases, it's better to:
- Add configuration options to existing features
- Use `EventConfig`, `RunConfig`, or `AssociationConfig` for customizable parameters (see [Configuration System Guide](03-configuration-system.md))
- Extend existing views with conditional behavior based on settings

Creating too many features makes the system harder to maintain and complicates the user interface for administrators.

---

## The Feature System

### Core Models

The feature system consists of three main models:

#### 1. FeatureModule

Groups related features together for organization in the UI.

**Fields:** `name`, `slug`, `icon`, `order`

**Example modules:** "writing", "casting", "accounting", "organization"

#### 2. Feature

Represents a specific functionality that can be enabled/disabled.

**Fields:** `name`, `descr`, `slug`, `order`, `overall`, `module`, `after_link`, `after_text`, `placeholder`, `hidden`

**Key concept - the `overall` field:**
- `overall=True`: Feature applies to the entire organization (e.g., organization settings, member management)
  - Can have both `exe_*` views (organization dashboard) and `orga_*` views (shown in all events)
- `overall=False`: Feature applies to individual events (e.g., character sheets, casting)
  - Only has `orga_*` views (event-specific dashboard)

**Example from fixtures:**
```yaml
- model: larpmanager.feature
  fields:
    name: Characters
    descr: Enables the creation, editing, and assignment of characters to registered participants
    slug: character
    overall: false  # Event-specific feature
    module: writing
    order: 1
    after_text: Now you can create characters
    after_link: orga_characters
    hidden: false
```

---

## Permission System

Permissions control what appears in the sidebar navigation and what users can access. There are two types of permissions corresponding to the two scopes.

### Models

#### 1. PermissionModule

Groups related permissions together in the sidebar.

**Fields:** `name`, `slug`, `icon`, `order`

**Example modules:** "organization", "event", "accounting"

#### 2. AssociationPermission

Creates sidebar links in the **organization dashboard** (`/exe/` URLs).

**Fields:** `name`, `slug`, `number`, `feature`, `module`, `descr`, `hidden`, `config`

**Important:**
- `slug`: Contains the **view name** (e.g., `exe_association`)
- `feature`: Must reference a Feature with `overall=True`
- Used for organization-wide functionality

**Example from fixtures:**
```yaml
- model: larpmanager.associationpermission
  fields:
    name: Organization
    descr: Manage the organization main settings
    slug: exe_association  # View name
    number: 2
    feature: exe_association  # References Feature with overall=True
    module: organization
    hidden: false
```

#### 3. EventPermission

Creates sidebar links in the **event dashboard** (`/orga/` URLs).

**Fields:** `name`, `slug`, `number`, `feature`, `module`, `descr`, `hidden`, `config`

**Important:**
- `slug`: Contains the **view name** (e.g., `orga_characters`)
- `feature`: Can reference either:
  - Feature with `overall=False` (event-specific feature)
  - Feature with `overall=True` (organization-wide feature shown in all events)
- Used for event-specific functionality

**Example from fixtures:**
```yaml
- model: larpmanager.eventpermission
  fields:
    name: Characters
    descr: Manage the event characters
    slug: orga_characters  # View name
    number: 11
    config: writing
    feature: character  # References Feature with overall=False
    module: writing
    hidden: false
```

---

## View Naming Conventions

LarpManager follows strict naming conventions for views based on their scope:

### Organization-Wide Views: `exe_*` prefix

Used for functionality that applies to the entire organization.

**Examples:**
- `exe_association` - Organization settings
- `exe_roles` - Organization role management
- `exe_config` - Organization configuration
- `exe_members` - Organization member list

### Event-Specific Views: `orga_*` prefix

Used for functionality that applies to individual events.

**Examples:**
- `orga_event` - Event settings
- `orga_characters` - Event character management
- `orga_casting` - Event casting system
- `orga_roles` - Event role management
- `orga_config` - Event configuration

**Convention Rule:** The prefix determines which dashboard the link appears in and helps maintain clear separation between organization and event functionality.

---

## Working with Fixtures

Features, permissions, and modules are stored as YAML fixtures in `larpmanager/fixtures/`. These fixtures ensure consistent deployment across all instances.

### Fixture Files

- `module.yaml` - FeatureModule definitions
- `feature.yaml` - Feature definitions
- `permission_module.yaml` - PermissionModule definitions
- `association_permission.yaml` - AssociationPermission definitions
- `event_permission.yaml` - EventPermission definitions
- `skin.yaml` - AssociationSkin configurations
- `payment_methods.yaml` - PaymentMethod configurations

### Management Commands

#### `export_features` (`larpmanager/management/commands/export_features.py`)

Exports the current database state to YAML fixtures.

**Usage:**
```bash
python manage.py export_features
```

**What it does:**
- Reads all Feature, FeatureModule, Permission, and related objects from the database
- Serializes them to YAML format
- Writes to `larpmanager/fixtures/*.yaml`
- Handles foreign keys by storing slugs instead of IDs
- Handles many-to-many relationships as lists of IDs

**When to run:**
- After creating new Features in the admin or code
- After creating new Permissions
- Before pushing changes to ensure fixtures are up-to-date

#### `import_features` (`larpmanager/management/commands/import_features.py`)

Imports YAML fixtures into the database, creating or updating records.

**Usage:**
```bash
python manage.py import_features
```

**What it does:**
- Reads YAML fixture files from `larpmanager/fixtures/`
- Creates or updates records using `update_or_create`
- Resolves foreign key relationships using slugs
- Sets many-to-many relationships

**When it runs automatically:**
- During deployment (called by `scripts/deploy.sh`)
- This ensures all instances have consistent features and permissions

---

## Step-by-Step Workflow

### When Creating a New Feature

Follow these steps when adding genuinely new functionality:

#### 1. Determine Feature Scope

**Ask yourself:** Does this functionality apply to:
- The entire organization? → Use `overall=True` and create `exe_*` views
- Individual events? → Use `overall=False` and create `orga_*` views

#### 2. Create the Feature

You can create features either through the Django admin or programmatically.

**Via Django Admin:**
1. Go to `/admin/larpmanager/feature/`
2. Create a new Feature with:
   - `name`: Descriptive name
   - `slug`: Unique identifier (lowercase, underscores)
   - `overall`: True for organization, False for event
   - `module`: Select appropriate module
   - `descr`: Clear description of what it enables
   - `after_link`: View name to redirect to after enabling
   - `after_text`: Success message

**Example for Event Feature:**
```python
# In a migration or data migration
Feature.objects.create(
    name="Characters",
    slug="character",
    descr="Enables the creation, editing, and assignment of characters to registered participants",
    overall=False,  # Event-specific
    module=FeatureModule.objects.get(slug="writing"),
    order=1,
    after_link="orga_characters",
    after_text="Now you can create characters"
)
```

#### 3. Create Views

Create views following naming conventions. For detailed information on structuring views, see the [Roles and Context Guide](02-roles-and-context.md).

**For event-specific features (overall=False):**

```python
# In larpmanager/views/...
from django.contrib.auth.decorators import login_required
from larpmanager.utils.core.base import check_event_context


@login_required
def orga_characters(request, event_slug):
    """Manage characters for an event."""
    # This checks permissions and provides context
    context = check_event_context(request, event_slug, permission_slug="orga_characters")

    characters = Character.objects.filter(event=context["event"])
    context["characters"] = characters

    return render(request, 'orga/characters.html', context)
```

**For organization-wide features (overall=True):**

```python
# In larpmanager/views/...
from django.contrib.auth.decorators import login_required
from larpmanager.utils.core.base import check_association_context


@login_required
def exe_members(request):
    """Manage organization-wide members."""
    # This checks permissions and provides context
    context = check_association_context(request, permission_slug="exe_members")

    members = Member.objects.filter(association_id=context["association_id"])
    context["members"] = members

    return render(request, 'exe/members.html', context)
```

**Important:** Always use the appropriate context helper function:
- `check_event_context(request, event_slug, permission_slug=...)` for `orga_*` views (checks EventPermission)
- `check_association_context(request, permission_slug=...)` for `exe_*` views (checks AssociationPermission)

See [Roles and Context Guide](02-roles-and-context.md) for complete documentation on context functions.

#### 4. Create Permissions for Sidebar Links

Permissions determine what appears in the sidebar navigation.

**For event-specific features:**
```python
# Via admin or migration
EventPermission.objects.create(
    name="Characters",
    slug="orga_characters",  # View name
    descr="Manage the event characters",
    feature=Feature.objects.get(slug="character"),
    module=PermissionModule.objects.get(slug="writing"),
    number=11,  # Order in sidebar
    config="writing"
)
```

**For organization-wide features:**
```python
# Via admin or migration
AssociationPermission.objects.create(
    name="Organization",
    slug="exe_association",  # View name
    descr="Manage the organization main settings",
    feature=Feature.objects.get(slug="exe_association"),
    module=PermissionModule.objects.get(slug="organization"),
    number=2,  # Order in sidebar
    config="interface"
)
```

#### 5. Add URL Patterns

Add URL patterns for your views in `larpmanager/urls.py`:

```python
# Event-specific URL (includes event_slug)
path('<slug:event_slug>/characters/', orga_characters, name='orga_characters'),

# Organization-wide URL (no event_slug)
path('exe/association/', exe_association, name='exe_association'),
```

#### 6. Export Fixtures

After creating your features and permissions:

```bash
python manage.py export_features
```

This updates the YAML fixtures in `larpmanager/fixtures/` with your new definitions.

#### 7. Test Thoroughly

- Verify the feature appears in the features list
- Test enabling/disabling the feature
- Verify sidebar links appear when feature is enabled
- Test role-based access to the views
- Run the test suite: `pytest`

#### 8. Commit Changes

Your commit should include:
- Updated fixture files (`larpmanager/fixtures/*.yaml`)
- New view implementations
- URL patterns
- Any templates or static files
- Tests covering the new functionality

---

## Examples

### Example 1: Event-Specific Feature (Characters)

From `larpmanager/fixtures/feature.yaml`:

```yaml
- model: larpmanager.feature
  fields:
    name: Characters
    descr: Enables the creation, editing, and assignment of characters to registered participants
    slug: character
    overall: false  # Event-specific
    module: writing
    order: 1
    after_text: Now you can create characters
    after_link: orga_characters
    hidden: false
```

**Corresponding EventPermission:**

```yaml
- model: larpmanager.eventpermission
  fields:
    name: Characters
    descr: Manage the event characters
    slug: orga_characters  # View name
    number: 11
    config: writing
    feature: character  # References the feature above
    module: writing
    hidden: false
```

This creates:
- Feature available per-event (overall=false)
- View named `orga_characters` (event-specific prefix)
- Sidebar link in the event dashboard under "writing" module
- When enabled, redirects to the character management view

### Example 2: Organization-Wide Feature

From `larpmanager/fixtures/association_permission.yaml:1-10`:

```yaml
- model: larpmanager.associationpermission
  fields:
    name: Organization
    descr: Manage the organization main settings
    slug: exe_association  # View name
    feature: exe_association  # Must reference overall=True feature
    module: organization
    number: 2
```

This creates:
- Sidebar link in organization dashboard
- Links to `exe_association` view
- Requires `exe_association` feature with `overall=True`

### Example 3: Creating a Feature Programmatically

```python
# In a data migration or management command
from larpmanager.models.base import Feature, FeatureModule
from larpmanager.models.access import EventPermission, PermissionModule

# 1. Create the feature
feature = Feature.objects.create(
    name="Character Diary",
    slug="character_diary",
    descr="Allows players to write diary entries for their characters",
    overall=False,  # Event-specific
    module=FeatureModule.objects.get(slug="writing"),
    order=250,
    after_link="orga_character_diary",
    after_text="Now you can enable character diaries for this event"
)

# 2. Create the permission (sidebar link)
EventPermission.objects.create(
    name="Character Diary",
    slug="orga_character_diary",  # View name
    descr="Manage character diary settings",
    feature=feature,
    module=PermissionModule.objects.get(slug="writing"),
    number=260
)

# 3. Don't forget to run: python manage.py export_features
```

---

## Best Practices

### Do:
- ✅ Create features only for genuinely new, independent functionality
- ✅ Use `overall=True` for organization-wide features
- ✅ Use `overall=False` for event-specific features
- ✅ Follow naming conventions (`orga_*` vs `exe_*`)
- ✅ Run `export_features` before committing
- ✅ Write tests for new features
- ✅ Keep feature descriptions clear and concise

### Don't:
- ❌ Create features for minor variations (use config options instead)
- ❌ Mix organization and event concerns in a single feature
- ❌ Forget to run `export_features` after changes
- ❌ Add fields to models that not every instance uses (use Config models instead)
- ❌ Create views without corresponding permissions
- ❌ Use non-standard view name prefixes

---

## Troubleshooting

### Feature doesn't appear in admin
- Check that `hidden=False`
- Verify the feature was saved to the database
- Run `import_features` to ensure fixtures are loaded

### Sidebar link doesn't appear
- Verify the permission's `feature` matches the feature slug
- Check that the user's role has the permission
- Ensure `overall` matches the permission type (AssociationPermission vs EventPermission)

### Import fails with "missing slugs"
- Ensure all referenced features/modules exist in the database
- Check fixture files for typos in slug references
- Run `export_features` to generate valid fixtures

### View raises 404
- Verify URL pattern is registered
- Check view name matches permission slug
- Ensure proper URL parameters (event_slug for orga_* views)

---

## Related Documentation

- **[Roles and Context Guide](02-roles-and-context.md)** - How to structure views with context and permissions
- **[Configuration System Guide](03-configuration-system.md)** - How to add settings without model fields
- **[Localization Guide](04-localization.md)** - How to write translatable code
- **[Playwright Testing Guide](05-playwright-testing.md)** - How to write E2E tests for new features
- [Contributing Guide](../README.md#contributing) - General contribution workflow
- [Architecture Overview](../CLAUDE.md#architecture-overview) - System architecture
- [Testing Guide](../CLAUDE.md#testing-strategy) - Testing approaches
- Django Admin: `/admin/larpmanager/feature/` - Manage features
- Django Admin: `/admin/larpmanager/eventpermission/` - Manage event permissions
- Django Admin: `/admin/larpmanager/associationpermission/` - Manage org permissions

---

## Summary

The LarpManager feature system provides flexible, modular functionality control at both organization and event levels. When adding new features:

1. **Decide if you really need a new feature** (prefer extending existing ones)
2. **Determine scope** (organization-wide or event-specific)
3. **Follow naming conventions** (`exe_*` or `orga_*`)
4. **Create matching permissions** for sidebar navigation
5. **Implement views with proper context** (see [Roles and Context Guide](02-roles-and-context.md))
6. **Export fixtures** before committing
7. **Test thoroughly** including role-based access

By following these guidelines, you'll maintain consistency with the existing codebase and make it easier for other developers to understand and extend your work.

**Next steps:** Read the [Roles and Context Guide](02-roles-and-context.md) to learn how to properly structure your views with permission checks and context handling.
