# Developer Guide: Configuration System

This guide explains how to use the configuration system to add customizable settings without modifying model fields.

**Why use configurations instead of model fields?** As mentioned in the [Features and Permissions Guide](01-features-and-permissions.md), you should only add fields to models if they're used by **every** instance. For optional or feature-specific settings, use the configuration system instead.

**Related guides:**
- [Features and Permissions Guide](01-features-and-permissions.md) - When to use configs vs model fields
- [Roles and Context Guide](02-roles-and-context.md) - How to access configuration in views
- [Localization Guide](04-localization.md) - Writing translatable configuration labels
- [Playwright Testing Guide](05-playwright-testing.md) - Testing configuration options

## Table of Contents

1. [Overview](#overview)
2. [Configuration Models](#configuration-models)
3. [Reading Configuration Values](#reading-configuration-values)
4. [Adding New Configurations](#adding-new-configurations)
5. [Configuration Forms](#configuration-forms)
6. [Best Practices](#best-practices)
7. [Examples](#examples)

---

## Overview

The configuration system allows storing key-value pairs for different entities without adding database columns. This provides flexibility for:

- Feature-specific settings that not all organizations/events use
- User preferences and customizations
- Settings that vary between instances
- Optional functionality toggles

### Key Benefits

✅ **Flexible** - Add settings without migrations
✅ **Scalable** - Only stores values that are actually set
✅ **Cached** - Configuration values are cached for performance
✅ **Type-safe** - Automatic type conversion based on default values
✅ **Clean models** - Keeps models focused on core fields

---

## Configuration Models

LarpManager provides five configuration models for different scopes:

### 1. AssociationConfig

Store organization-wide settings.

**Fields:** `name`, `value`, `association`

**Use for:**
- Organization preferences
- Interface settings
- Email notification preferences
- Calendar display options

**Example configurations:**
- `calendar_past_events` - Show past events in calendar
- `mail_cc` - Send carbon copy of emails
- `require_birthdate` - Require birthdate for members

### 2. EventConfig

Store event-specific settings.

**Fields:** `name`, `value`, `event`

**Use for:**
- Event-specific features
- Character creation settings
- Writing system configuration
- Registration options

**Example configurations:**
- `character_creation_deadline` - Deadline for character creation
- `writing_field_visibility` - Control field visibility for players
- `max_characters_per_user` - Limit characters per participant

### 3. RunConfig

Store run-specific settings (individual event instances).

**Fields:** `name`, `value`, `run`

**Use for:**
- Run-specific overrides
- Instance-specific settings
- Temporary configurations

**Example configurations:**
- `show_character` - Display character information
- `show_faction` - Show faction details
- `show_trait` - Display trait information

### 4. MemberConfig

Store user-specific settings and preferences.

**Fields:** `name`, `value`, `member`

**Use for:**
- User interface preferences
- Personal settings
- Notification preferences

**Example configurations:**
- `interface_collapse_sidebar` - Sidebar collapsed state
- `notification_email` - Email notification preference
- `language_preference` - Preferred language

### 5. CharacterConfig

Store character-specific settings.

**Fields:** `name`, `value`, `character`

**Use for:**
- Character-specific options
- Player preferences for characters
- Character metadata

---

## Reading Configuration Values

The configuration system provides helper functions to read values with automatic type conversion and caching.

### get_event_config()

Get configuration for an event with caching.

**Location:** `larpmanager/cache/config.py`

**Signature:**
```python
def get_event_config(
    event_id: int,
    config_name: str,
    default_value: any = None,
    context: dict | None = None,
    bypass_cache: bool = False
) -> any
```

**Parameters:**
- `event_id` - Event ID to get configuration for
- `config_name` - Configuration key to retrieve
- `default_value` - Default value if not set (also determines return type)
- `context` - Optional context dict for multi-config caching
- `bypass_cache` - If True, fetch from database (useful for background tasks)

**Returns:** Configuration value with automatic type conversion

**Example usage:**
```python
from larpmanager.cache.config import get_event_config

def orga_characters(request, event_slug):
    context = check_event_context(request, event_slug, permission_slug="orga_characters")

    # Get boolean config with default False
    require_backstory = get_event_config(
        context["event"].id,
        "character_require_backstory",
        False,
        context
    )

    # Get string config with default None
    backstory_min_words = get_event_config(
        context["event"].id,
        "character_backstory_min_words",
        "500",
        context
    )

    if require_backstory:
        context["backstory_required"] = True
        context["min_words"] = backstory_min_words

    return render(request, "orga/characters.html", context)
```

**Type conversion:**
- If `default_value` is `bool` → converts "True"/"False" string to boolean
- If value is empty or "None" → returns `default_value`
- Otherwise → returns the string value

### get_association_config()

Get configuration for an organization with caching.

**Signature:**
```python
def get_association_config(
    association_id: int,
    config_name: str,
    default_value: any = None,
    context: dict | None = None,
    bypass_cache: bool = False
) -> any
```

**Parameters:** Same as `get_event_config()` but for associations

**Example usage:**
```python
from larpmanager.cache.config import get_association_config

def exe_members(request):
    context = check_association_context(request, permission_slug="exe_members")

    # Check if birthdate is required
    require_birthdate = get_association_config(
        context["association_id"],
        "require_birthdate",
        False,
        context
    )

    context["require_birthdate"] = require_birthdate
    return render(request, "exe/members.html", context)
```

### get_element_config()

Get configuration for any model instance.

**Signature:**
```python
def get_element_config(
    element: Model,
    config_name: str,
    default_value: any,
    bypass_cache: bool = False
) -> any
```

**Parameters:**
- `element` - Model instance (Event, Association, Run, Member, Character)
- `config_name` - Configuration key
- `default_value` - Default value and type indicator
- `bypass_cache` - Whether to skip cache

**Example usage:**
```python
from larpmanager.cache.config import get_element_config

def character_detail(request, character_id):
    character = Character.objects.get(id=character_id)

    # Get character-specific setting
    show_secrets = get_element_config(
        character,
        "show_secrets_to_player",
        False
    )

    context = {
        "character": character,
        "show_secrets": show_secrets
    }
    return render(request, "character_detail.html", context)
```

### Context Caching

When reading multiple configurations, pass the `context` dictionary to enable caching:

```python
def my_view(request, event_slug):
    context = check_event_context(request, event_slug, permission_slug="orga_view")
    event_id = context["event"].id

    # First call: fetches from cache/database
    setting1 = get_event_config(event_id, "setting1", False, context)

    # Subsequent calls: reuses cached data
    setting2 = get_event_config(event_id, "setting2", True, context)
    setting3 = get_event_config(event_id, "setting3", "default", context)

    # All three reads use the same cached config dict
```

---

## Adding New Configurations

To add a new configuration option that users can set, you need to modify the appropriate configuration form.

### Step 1: Choose the Right Form

Depending on scope, edit the appropriate form:

- **Organization settings** → `ExeConfigForm` in `larpmanager/forms/association.py`
- **Event settings** → `OrgaConfigForm` in `larpmanager/forms/event.py`
- **Run settings** → `OrgaRunConfigForm` in `larpmanager/forms/event.py`

### Step 2: Add Configuration Field

Configuration forms extend `ConfigForm` and use the `set_configs()` method to define fields.

**Basic pattern:**
```python
def set_configs(self) -> None:
    # Create or select a section
    self.set_section("section_slug", _("Section Display Name"))

    # Add configuration field
    self.add_configs(
        "config_name",           # Configuration key (stored in database)
        ConfigType.BOOL,         # Field type
        _("Field Label"),        # User-visible label
        _("Help text")           # Help text explaining the setting
    )
```

### Configuration Types

Available in `ConfigType` enum:

- `ConfigType.BOOL` - Checkbox (True/False)
- `ConfigType.TEXT` - Short text input
- `ConfigType.TEXTAREA` - Multi-line text
- `ConfigType.NUMBER` - Numeric input
- `ConfigType.SELECT` - Dropdown selection
- `ConfigType.DATE` - Date picker
- `ConfigType.DATETIME` - Date and time picker

### Step 3: Update Form's set_configs Method

**Example: Adding a new event configuration**

```python
# In larpmanager/forms/event.py

class OrgaConfigForm(ConfigForm):
    # ... existing code ...

    def set_configs(self) -> None:
        # Existing configurations...

        # Add new section for character settings
        self.set_section("characters", _("Character Settings"))

        # Add boolean config
        self.add_configs(
            "character_require_backstory",
            ConfigType.BOOL,
            _("Require backstory"),
            _("If checked: players must write a backstory for their character")
        )

        # Add text config
        self.add_configs(
            "character_backstory_min_words",
            ConfigType.TEXT,
            _("Minimum backstory words"),
            _("Minimum number of words required in character backstory")
        )

        # Add select config
        self.add_configs(
            "character_approval_mode",
            ConfigType.SELECT,
            _("Character approval mode"),
            _("How characters should be approved"),
            choices=[
                ("auto", _("Automatic approval")),
                ("manual", _("Manual approval required")),
                ("none", _("No approval needed"))
            ]
        )
```

### Sections

Sections group related configurations in the UI. Use `set_section()` to create or select a section:

```python
self.set_section("section_slug", _("Section Title"))
```

**Common sections:**
- `interface` - UI and display settings
- `email` - Email notification settings
- `calendar` - Calendar display options
- `characters` - Character-related settings
- `registration` - Registration settings
- `writing` - Writing system settings

---

## Best Practices

### Do:

✅ **Use configurations for optional settings**
```python
# Good - optional feature-specific setting
require_backstory = get_event_config(event_id, "require_backstory", False, context)

# Bad - adding field that not all events use
# class Event(models.Model):
#     require_backstory = models.BooleanField(default=False)  # ❌
```

✅ **Provide sensible defaults**
```python
# Good - default value makes sense if not configured
max_chars = get_event_config(event_id, "max_characters_per_user", 3, context)

# Bad - no default could cause issues
max_chars = get_event_config(event_id, "max_characters_per_user", None, context)
if max_chars is None:  # Extra handling needed
    max_chars = 3
```

✅ **Use meaningful config names**
```python
# Good - clear, descriptive name
get_event_config(event_id, "character_creation_deadline", None, context)

# Bad - unclear abbreviation
get_event_config(event_id, "char_cre_dl", None, context)
```

✅ **Pass context for multiple reads**
```python
# Good - reuses cached data
setting1 = get_event_config(event_id, "setting1", False, context)
setting2 = get_event_config(event_id, "setting2", True, context)

# Less efficient - separate cache lookups
setting1 = get_event_config(event_id, "setting1", False)
setting2 = get_event_config(event_id, "setting2", True)
```

✅ **Group related configs in sections**
```python
# Good - related settings grouped
self.set_section("characters", _("Characters"))
self.add_configs("character_creation_deadline", ...)
self.add_configs("character_require_backstory", ...)
self.add_configs("character_max_per_user", ...)
```

✅ **Add helpful descriptions**
```python
# Good - explains what the setting does
self.add_configs(
    "mail_cc",
    ConfigType.BOOL,
    _("Carbon copy"),
    _("If checked: Sends the main mail a copy of all mails sent to participants")
)

# Bad - unclear what it does
self.add_configs("mail_cc", ConfigType.BOOL, _("CC"), _("CC emails"))
```

### Don't:

❌ **Don't use configs for core functionality**
```python
# Bad - event name is core data, should be model field
event_name = get_event_config(event_id, "event_name", "", context)

# Good - use model field for core data
event_name = event.name
```

❌ **Don't forget type conversion**
```python
# Bad - treating boolean as string
if get_event_config(event_id, "setting", False) == "True":  # ❌

# Good - type is converted automatically
if get_event_config(event_id, "setting", False):  # ✅
```

❌ **Don't bypass cache unnecessarily**
```python
# Bad - bypassing cache in regular view
setting = get_event_config(event_id, "setting", False, bypass_cache=True)

# Good - only bypass in background tasks
# In a Celery task or management command:
setting = get_event_config(event_id, "setting", False, bypass_cache=True)
```

❌ **Don't use configs for frequently changing data**
```python
# Bad - participant count changes often, use database query
participants = get_event_config(event_id, "participant_count", 0)

# Good - query for current data
participants = Registration.objects.filter(run__event_id=event_id).count()
```

---

## Examples

### Example 1: Adding Event Configuration

**Requirement:** Add setting to require character backstory with minimum word count.

**Step 1: Add to form**

```python
# In larpmanager/forms/event.py - OrgaConfigForm

def set_configs(self) -> None:
    # ... existing sections ...

    self.set_section("characters", _("Characters"))

    # Add boolean toggle
    self.add_configs(
        "character_require_backstory",
        ConfigType.BOOL,
        _("Require backstory"),
        _("If checked: players must provide a backstory for their character")
    )

    # Add text field for minimum words
    self.add_configs(
        "character_backstory_min_words",
        ConfigType.TEXT,
        _("Minimum backstory words"),
        _("Minimum number of words required (leave empty for no minimum)")
    )
```

**Step 2: Use in view**

```python
# In a character creation view
from larpmanager.cache.config import get_event_config

def character_create(request, event_slug):
    context = get_event_context(request, event_slug)

    # Read configuration
    require_backstory = get_event_config(
        context["event"].id,
        "character_require_backstory",
        False,
        context
    )

    min_words = get_event_config(
        context["event"].id,
        "character_backstory_min_words",
        None,
        context
    )

    # Apply validation
    if require_backstory:
        context["backstory_required"] = True
        if min_words:
            context["backstory_min_words"] = int(min_words)

    return render(request, "character_create.html", context)
```

**Step 3: Use in template**

```html
<form method="post">
    {% csrf_token %}

    <label for="backstory">
        Backstory
        {% if backstory_required %}*{% endif %}
    </label>

    <textarea
        name="backstory"
        id="backstory"
        {% if backstory_required %}required{% endif %}
    ></textarea>

    {% if backstory_min_words %}
        <p class="help-text">
            Minimum {{ backstory_min_words }} words required
        </p>
    {% endif %}

    <button type="submit">Create Character</button>
</form>
```

### Example 2: Adding Organization Configuration

**Requirement:** Add setting to show/hide member birthdates in the member list.

**Step 1: Add to form**

```python
# In larpmanager/forms/association.py - ExeConfigForm

def set_config_members(self) -> None:
    """Configure member-related settings."""
    self.set_section("members", _("Members"))

    # Add boolean toggle
    self.add_configs(
        "members_show_birthdate",
        ConfigType.BOOL,
        _("Show birthdates"),
        _("If checked: display member birthdates in the member list")
    )
```

**Step 2: Use in view**

```python
# In larpmanager/views/exe/member.py

from larpmanager.cache.config import get_association_config

@login_required
def exe_members(request):
    context = check_association_context(request, permission_slug="exe_members")

    # Read configuration
    show_birthdate = get_association_config(
        context["association_id"],
        "members_show_birthdate",
        True,  # Default to showing
        context
    )

    # Get members
    members = Member.objects.filter(
        association_id=context["association_id"]
    )

    context["members"] = members
    context["show_birthdate"] = show_birthdate

    return render(request, "exe/members.html", context)
```

**Step 3: Use in template**

```html
<table>
    <thead>
        <tr>
            <th>Name</th>
            <th>Email</th>
            {% if show_birthdate %}
                <th>Birthdate</th>
            {% endif %}
        </tr>
    </thead>
    <tbody>
        {% for member in members %}
            <tr>
                <td>{{ member.name }}</td>
                <td>{{ member.email }}</td>
                {% if show_birthdate %}
                    <td>{{ member.birthdate|date:"Y-m-d" }}</td>
                {% endif %}
            </tr>
        {% endfor %}
    </tbody>
</table>
```

### Example 3: Feature-Specific Configuration

**Requirement:** Add deadline configuration when "character_assignment" feature is enabled.

```python
# In larpmanager/forms/event.py - OrgaConfigForm

def set_configs(self) -> None:
    # ... existing configurations ...

    # Only show if feature is enabled
    if "character_assignment" in self.instance.get_features():
        self.set_section("assignment", _("Character Assignment"))

        self.add_configs(
            "assignment_deadline",
            ConfigType.DATETIME,
            _("Assignment deadline"),
            _("Players must accept their character by this date/time")
        )

        self.add_configs(
            "assignment_auto_reject",
            ConfigType.BOOL,
            _("Auto-reject after deadline"),
            _("If checked: automatically reject unaccepted characters after deadline")
        )
```

### Example 4: Multiple Config Reads

**Efficient pattern for reading multiple configurations:**

```python
def orga_registration_form(request, event_slug):
    context = check_event_context(request, event_slug, permission_slug="orga_registration")
    event_id = context["event"].id

    # Pass context to reuse cached config data
    configs = {
        "require_phone": get_event_config(event_id, "reg_require_phone", False, context),
        "require_address": get_event_config(event_id, "reg_require_address", False, context),
        "require_dietary": get_event_config(event_id, "reg_require_dietary", True, context),
        "max_participants": get_event_config(event_id, "reg_max_participants", None, context),
    }

    context.update(configs)
    return render(request, "orga/registration_form.html", context)
```

---

## Summary

The configuration system in LarpManager provides flexible, cached key-value storage for:

1. **Organization settings** via AssociationConfig
2. **Event settings** via EventConfig
3. **Run settings** via RunConfig
4. **User preferences** via MemberConfig
5. **Character settings** via CharacterConfig

**Key points:**
- Use configurations for optional/feature-specific settings
- Provide sensible defaults for all configurations
- Pass context dictionary for efficient multi-read caching
- Add configurations through ConfigForm classes
- Read with `get_event_config()`, `get_association_config()`, or `get_element_config()`
- Automatic type conversion based on default value type

**Related guides:**
- [Features and Permissions Guide](01-features-and-permissions.md) - When to use configs vs model fields
- [Roles and Context Guide](02-roles-and-context.md) - How to access config in views
- [Playwright Testing Guide](05-playwright-testing.md) - Testing configuration options

By using the configuration system appropriately, you keep models clean while maintaining flexibility for optional features and user customization.
