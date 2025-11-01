# Developer Guide: Roles and Context

This guide explains how to structure views using the context system and how roles connect to permissions.

## Table of Contents

1. [Overview](#overview)
2. [The Context Dictionary](#the-context-dictionary)
3. [Context Helper Functions](#context-helper-functions)
4. [Roles and Permissions](#roles-and-permissions)
5. [Usage Examples](#usage-examples)
6. [Best Practices](#best-practices)

---

## Overview

Every view in LarpManager should obtain a **context dictionary** from the request object. This dictionary contains common elements needed for rendering templates and enforcing permissions, including:

- Association and event information
- User membership and permissions
- Feature flags
- Configuration settings
- UI preferences

The context system provides helper functions that:
- Build the context dictionary with appropriate data
- Check permissions automatically
- Validate feature access
- Handle common error cases

---

## The Context Dictionary

The context is a Python dictionary containing commonly used elements. It's passed to templates and used throughout the view logic.

### Common Context Keys

After calling a context helper function, the dictionary typically contains:

**Association Data:**
- `association_id` - Current association ID
- `association_slug` - Association URL slug
- `features` - Set of enabled feature slugs
- `token_name`, `credit_name` - Configured names for tokens/credits system

**User Data:**
- `member` - Current Member object (or None if not logged in)
- `membership` - Membership object linking user to association
- `is_staff` - Boolean indicating Django staff status
- `interface_collapse_sidebar` - User's sidebar preference

**Event Data (when applicable):**
- `event` - Event object
- `run` - Run object (specific instance of an event)
- `event_slug` - Event URL slug

**Management Flags:**
- `manage` - Set to 1 for management views
- `exe_page` - Set to 1 for organization dashboard views
- `orga_page` - Set to 1 for event dashboard views
- `staff` - Set to "1" if user has character management access

**Permissions:**
- `association_permissions` - List of user's organization permissions
- `event_permissions` - List of user's event permissions

**Configuration:**
- `tutorial` - Tutorial identifier for the current view
- `config` - URL to configuration page (if available)

---

## Context Helper Functions

All context helper functions are located in `larpmanager/utils/base.py`.

### 1. get_context()

**Purpose:** Build basic context for views without event-specific or permission requirements.

**Use when:**
- Creating public pages
- Building base pages without specific permissions
- Views that don't require feature checks

**Function signature:**
```python
def get_context(request: HttpRequest, check_main_site: bool = False) -> dict
```

**Parameters:**
- `request` - HTTP request object
- `check_main_site` - If True, ensures page is only accessible on main site

**Returns:** Dictionary with association data, user info, and basic settings

**Example usage:**
```python
from larpmanager.utils.base import get_context

def public_page(request):
    """Simple public page without permission requirements."""
    context = get_context(request)
    # Add view-specific data to context
    context["page_title"] = "Public Page"
    return render(request, "public.html", context)
```

**What it provides:**
- Association information
- User membership data
- Feature flags
- TinyMCE configuration
- Basic UI settings

---

### 2. get_event_context()

**Purpose:** Get event context with optional feature validation.

**Use when:**
- Building event-specific views (user-facing)
- Need access to event/run objects
- Want to check if a feature is enabled
- Need registration status information

**Function signature:**
```python
def get_event_context(
    request,
    event_slug: str,
    signup: bool = False,
    feature_slug: str | None = None,
    include_status: bool = False
) -> dict
```

**Parameters:**
- `request` - HTTP request object
- `event_slug` - Event identifier from URL
- `signup` - If True, validates user can sign up for the event
- `feature_slug` - Optional feature slug to verify is enabled
- `include_status` - If True, includes detailed registration status

**Returns:** Dictionary with event context and optional validation

**Example usage:**
```python
from larpmanager.utils.base import get_event_context
from larpmanager.models.writing import Character

def event_character_gallery(request, event_slug):
    """Public character gallery - requires "character_gallery" feature."""
    # Get context and verify "character_gallery" feature is enabled
    # If feature is not enabled, this will raise FeatureError automatically
    context = get_event_context(
        request,
        event_slug,
        feature_slug="character_gallery"
    )

    # If we get here, the feature is enabled - no need to check again
    # Load published characters
    context["characters"] = Character.objects.filter(
        event=context["event"],
        published=True
    )

    return render(request, "event_gallery.html", context)
```

**What it provides (beyond get_context):**
- `event` - Event object
- `run` - Run object
- Event-specific features in `context["features"]`
- Registration status (if requested via `include_status=True`)
- User permissions for this event (if user has any)

**Important notes:**
- If `feature_slug` is provided and the feature is not enabled, this function raises `FeatureError` automatically
- This function does NOT enforce permissions - use `check_event_context()` for permission-protected views

---

### 3. check_event_context()

**Purpose:** Validate event permissions and prepare management context.

**Use when:**
- Creating `orga_*` views (event management)
- Need to verify user has specific EventPermission
- Building event dashboard pages

**Function signature:**
```python
def check_event_context(
    request,
    event_slug: str,
    permission_slug: str | list[str] | None = None
) -> dict
```

**Parameters:**
- `request` - HTTP request object
- `event_slug` - Event identifier from URL
- `permission_slug` - Permission slug(s) required to access view
  - Can be a single string: `"orga_characters"`
  - Can be a list: `["orga_characters", "orga_casting"]`
  - Can be None for basic event staff access check

**Returns:** Dictionary with event context and management flags

**Raises:**
- `PermissionError` - If user lacks required permission
- `FeatureError` - If required feature is not enabled

**Example usage:**
```python
from django.contrib.auth.decorators import login_required
from larpmanager.utils.base import check_event_context

@login_required
def orga_characters(request, event_slug):
    """Manage event characters - requires orga_characters permission."""
    # Check permission and get context
    context = check_event_context(request, event_slug, permission_slug="orga_characters")

    # If we get here, user has permission and feature is enabled
    # context["orga_page"] == 1
    # context["manage"] == 1

    # Get characters for this event
    characters = Character.objects.filter(event=context["event"])
    context["characters"] = characters

    return render(request, "orga/characters.html", context)
```

**What it provides (beyond get_event_context):**
- Permission validation (raises PermissionError if denied)
- Feature validation (raises FeatureError if not enabled)
- `orga_page` = 1 (marks as event management page)
- `manage` = 1 (marks as management view)
- `tutorial` - Tutorial identifier for the permission
- `config` - Configuration URL (if user has config access)
- Event permissions index for sidebar rendering

**Important:** Always use this for `orga_*` views that require specific permissions.

---

### 4. check_association_context()

**Purpose:** Validate organization permissions and prepare executive context.

**Use when:**
- Creating `exe_*` views (organization management)
- Need to verify user has specific AssociationPermission
- Building organization dashboard pages

**Function signature:**
```python
def check_association_context(
    request: HttpRequest,
    permission_slug: str
) -> dict
```

**Parameters:**
- `request` - HTTP request object
- `permission_slug` - AssociationPermission slug required to access view

**Returns:** Dictionary with association context and management flags

**Raises:**
- `PermissionError` - If user lacks required permission
- `FeatureError` - If required feature is not enabled

**Example usage:**
```python
from django.contrib.auth.decorators import login_required
from larpmanager.utils.base import check_association_context

@login_required
def exe_membership(request):
    """Manage organization memberships - requires exe_membership permission."""
    # Check permission and get context
    context = check_association_context(request, "exe_membership")

    # If we get here, user has permission and feature is enabled
    # context["exe_page"] == 1
    # context["manage"] == 1

    # Get memberships for this organization
    memberships = Membership.objects.filter(
        association_id=context["association_id"]
    )
    context["memberships"] = memberships

    return render(request, "exe/membership.html", context)
```

**What it provides (beyond get_context):**
- Permission validation (raises PermissionError if denied)
- Feature validation (raises FeatureError if not enabled)
- `exe_page` = 1 (marks as organization management page)
- `manage` = 1 (marks as management view)
- `tutorial` - Tutorial identifier for the permission
- `config` - Configuration URL (if user has config access)
- Association permissions index for sidebar rendering
- `is_sidebar_open` - Sidebar state from session

**Important:** Always use this for `exe_*` views that require specific permissions.

---

## Roles and Permissions

The permission system connects users to permissions through roles. Understanding this relationship is essential for working with the context system.

### The Role-Permission Relationship

```
User (Member)
    ↓
Role (EventRole or AssociationRole)
    ↓ (many-to-many)
Permission (EventPermission or AssociationPermission)
    ↓
Feature
```

### Event Roles and Permissions

**EventRole** - Defined in `larpmanager/models/access.py`

**Fields:** `name`, `event`, `number`, `members`, `permissions`

**Key relationships:**
- `members` - M2M to Member (users assigned this role)
- `permissions` - M2M to EventPermission (what this role can access)

**How it works:**
1. Organization staff creates EventRoles for an event (e.g., "Organizer", "Story Team", "Logistics")
2. They assign EventPermissions to each role (e.g., Organizer gets all permissions)
3. They assign Members to roles
4. When a user accesses an `orga_*` view, the system checks:
   - Does user have an EventRole for this event?
   - Does that role have the required EventPermission?
   - If yes → grant access; if no → PermissionError

**Example:**
```python
# EventRole: "Story Team" for "Vampire LARP 2025"
role = EventRole.objects.get(event=event, number=2)

# This role has these permissions:
role.permissions.all()  # [orga_characters, orga_plots, orga_casting]

# These users have this role:
role.members.all()  # [alice@example.com, bob@example.com]

# When Alice visits /vampire-larp-2025/characters/:
# → check_event_context(request, event_slug, permission_slug="orga_characters")
# → Granted because Alice is in Story Team role, which has that permission
```

### Association Roles and Permissions

**AssociationRole** - Defined in `larpmanager/models/access.py`

**Fields:** `name`, `association`, `number`, `members`, `permissions`

**Key relationships:**
- `members` - M2M to Member (users assigned this role)
- `permissions` - M2M to AssociationPermission (what this role can access)

**How it works:**
1. Organization creates AssociationRoles (e.g., "Executive Board", "Accountant", "Event Creator")
2. They assign AssociationPermissions to each role (e.g., Executive gets all permissions)
3. They assign Members to roles
4. When a user accesses an `exe_*` view, the system checks:
   - Does user have an AssociationRole for this organization?
   - Does that role have the required AssociationPermission?
   - If yes → grant access; if no → PermissionError

**Example:**
```python
# AssociationRole: "Executive Board"
role = AssociationRole.objects.get(association=association, number=1)

# This role has these permissions:
role.permissions.all()  # [exe_association, exe_roles, exe_config, exe_events, ...]

# These users have this role:
role.members.all()  # [admin@larp.org, president@larp.org]

# When admin@larp.org visits /exe/roles/:
# → check_association_context verifies user has exe_roles permission
# → Granted because user is in Executive Board role, which has that permission
```

### Permission Checking Flow

When you call `check_event_context(request, event_slug, permission_slug="orga_characters")`:

1. **Get user's roles for this event:**
   ```python
   user_roles = EventRole.objects.filter(
       event__slug=event_slug,
       members=request.user.member
   )
   ```

2. **Get permissions from those roles:**
   ```python
   user_permissions = EventPermission.objects.filter(
       roles__in=user_roles
   )
   ```

3. **Check if required permission is in user's permissions:**
   ```python
   if "orga_characters" not in [p.slug for p in user_permissions]:
       raise PermissionError()
   ```

4. **Get the feature linked to this permission:**
   ```python
   permission = EventPermission.objects.get(slug="orga_characters")
   feature = permission.feature
   ```

5. **Check if feature is enabled for this event:**
   ```python
   if feature.slug not in event.enabled_features:
       raise FeatureError()
   ```

The same flow applies to `check_association_context()` but with AssociationRole and AssociationPermission.

### Creating and Managing Roles

Roles are typically managed through the dashboard views:

**Event roles:** Created at `Event -> Roles` (requires `orga_roles` permission)
**Association roles:** Created at `Organization ` (requires `exe_roles` permission)

When creating a role:
1. Give it a descriptive name
2. Assign relevant permissions
3. Add members who should have this role

**Example role setup:**
```python
# Create a "Story Team" role for an event
story_role = EventRole.objects.create(
    event=event,
    name="Story Team",
    number=2
)

# Assign permissions
story_permissions = EventPermission.objects.filter(
    slug__in=["orga_characters", "orga_plots", "orga_casting"]
)
story_role.permissions.set(story_permissions)

# Add members
story_role.members.add(alice, bob)
```

---

## Usage Examples

### Example 1: Basic Event Management View

```python
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from larpmanager.utils.base import check_event_context
from larpmanager.models.event import Character

@login_required
def orga_characters(request, event_slug):
    """Manage characters for an event.

    Requires: orga_characters permission (linked to "character" feature)
    """
    # Check permission and get context
    context = check_event_context(request, event_slug, permission_slug="orga_characters")

    # Load characters for this event
    context["characters"] = Character.objects.filter(
        event=context["event"]
    ).order_by("name")

    # Render template with context
    return render(request, "orga/characters.html", context)
```

### Example 2: Organization Management View

```python
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from larpmanager.utils.base import check_association_context
from larpmanager.models.member import Membership

@login_required
def exe_membership(request):
    """Manage organization memberships.

    Requires: exe_membership permission (linked to "exe_membership" feature)
    """
    # Check permission and get context
    context = check_association_context(request, permission_slug="exe_membership")

    # Load memberships for this organization
    context["memberships"] = Membership.objects.filter(
        association_id=context["association_id"]
    ).select_related("member")

    # Render template with context
    return render(request, "exe/membership.html", context)
```

### Example 3: Public Event Page with Feature Check

```python
from django.shortcuts import render
from larpmanager.utils.base import get_event_context
from larpmanager.models.writing import Character

def event_character_gallery(request, event_slug):
    """Public character gallery for an event.

    No permission required, but requires "character_gallery" feature.
    """
    # Get event context and verify feature is enabled
    # Raises FeatureError if "character_gallery" is not enabled
    context = get_event_context(
        request,
        event_slug,
        feature_slug="character_gallery"
    )

    # If we get here, feature is enabled - load published characters
    context["characters"] = Character.objects.filter(
        event=context["event"],
        published=True
    )

    return render(request, "user/character_gallery.html", context)
```

### Example 4: View with Multiple Permission Options

```python
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from larpmanager.utils.base import check_event_context

@login_required
def orga_character_detail(request, event_slug, character_id):
    """View character details.

    Requires: orga_characters OR orga_casting permission
    """
    # Check if user has either permission
    context = check_event_context(
        request,
        event_slug,
        permission_slug=["orga_characters", "orga_casting"]
    )

    # Load character
    character = Character.objects.get(
        id=character_id,
        event=context["event"]
    )
    context["character"] = character

    return render(request, "orga/character_detail.html", context)
```

### Example 5: View Without Permission Requirements

```python
from django.shortcuts import render
from larpmanager.utils.base import get_context

def home(request):
    """Homepage - no specific permissions needed."""
    # Get basic context
    context = get_context(request)

    # Add homepage-specific data
    context["page_title"] = "Welcome to LarpManager"

    return render(request, "home.html", context)
```

---

## Best Practices

### Do:

✅ **Always use context helpers** - Don't manually build context dictionaries
```python
# Good
context = check_event_context(request, event_slug, permission_slug="orga_characters")

# Bad
context = {"event": Event.objects.get(slug=event_slug)}
```

✅ **Use appropriate context function for view type:**
- `get_context()` - Public/basic views
- `get_event_context()` - Event views without permission requirements
- `check_event_context(request, event_slug, permission_slug=...)` - Event management views (`orga_*`)
- `check_association_context(request, permission_slug=...)` - Organization management views (`exe_*`)

✅ **Add `@login_required` decorator for protected views:**
```python
from django.contrib.auth.decorators import login_required

@login_required
def orga_characters(request, event_slug):
    context = check_event_context(request, event_slug, permission_slug="orga_characters")
    # ...
```

✅ **Handle context errors appropriately** - The context functions raise specific exceptions:
```python
# These are caught by middleware and show appropriate error pages:
# - PermissionError → "You don't have permission"
# - FeatureError → "Feature not enabled"
# - MembershipError → "You're not a member"
```

✅ **Pass correct permission slug to check functions:**
```python
# Permission slug must match the view name
def orga_characters(request, event_slug):
    context = check_event_context(request, event_slug, permission_slug="orga_characters")
```

✅ **Use context data in templates:**
```html
{% if manage %}
  <div class="management-toolbar">
    <!-- Management controls -->
  </div>
{% endif %}

{% if "character_gallery" in features %}
  <a href="{% url 'character_gallery' event.slug %}">View Gallery</a>
{% endif %}
```

### Don't:

❌ **Don't bypass permission checks:**
```python
# Bad - no permission check
def orga_characters(request, event_slug):
    event = Event.objects.get(slug=event_slug)
    # Anyone can access this!
```

❌ **Don't use wrong context function:**
```python
# Bad - should use check_event_context for orga_ view
def orga_characters(request, event_slug):
    context = get_event_context(request, event_slug)  # No permission check!
```

❌ **Don't manually check permissions:**
```python
# Bad - use check_event_context instead
def orga_characters(request, event_slug):
    context = get_event_context(request, event_slug)
    if not has_permission(request, "orga_characters"):  # Don't do this
        raise PermissionError()
```

❌ **Don't forget event_slug parameter for event views:**
```python
# Bad - event views need event_slug
def orga_characters(request):  # Missing event_slug!
    # Can't call check_event_context without event_slug
```

❌ **Don't create views without context:**
```python
# Bad - always use context system
def some_view(request):
    return render(request, "template.html", {})  # No context!
```

---

## Summary

The context system in LarpManager:

1. **Provides consistent data structure** - All views use the same context format
2. **Enforces permissions automatically** - Using the check functions ensures security
3. **Validates feature access** - Features are checked before granting access
4. **Simplifies view logic** - Common patterns are handled by helper functions
5. **Connects roles to permissions** - Users get access through role membership

**Key takeaways:**
- Use `check_event_context(request, event_slug, permission_slug=...)` for `orga_*` views
- Use `check_association_context(request, permission_slug=...)` for `exe_*` views
- Use `get_event_context()` for event views without permission requirements
- Use `get_context()` for basic views
- Both check functions use the same parameter name: `permission_slug`
- Roles connect members to permissions through M2M relationships
- Always add `@login_required` decorator for protected views

**Related guides:**
- [Features and Permissions Guide](01-features-and-permissions.md) - Creating features and permissions
- [Configuration System Guide](03-configuration-system.md) - Adding customizable settings
- [Localization Guide](04-localization.md) - Writing translatable code
- [Playwright Testing Guide](05-playwright-testing.md) - Writing E2E tests for views
