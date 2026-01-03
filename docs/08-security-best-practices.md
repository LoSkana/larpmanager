# Security Best Practices

This guide outlines critical security practices that must be followed when developing features for LarpManager.

## Table of Contents

1. [UUID Usage (Required)](#uuid-usage-required)
2. [SQL Injection Prevention](#sql-injection-prevention)
3. [XSS Prevention](#xss-prevention)
4. [CSRF Protection](#csrf-protection)
5. [Security Checklist](#security-checklist)

---

## UUID Usage (Required)

### Never Use Direct IDs in URLs or Frontend

**CRITICAL RULE:** Direct database IDs (primary keys) must NEVER be exposed in URLs or frontend code. Always use UUIDs instead.

### Why UUIDs Are Required

Using direct database IDs creates several security vulnerabilities:

1. **Enumeration attacks**: Attackers can iterate through sequential IDs to access or discover resources
2. **Information disclosure**: Sequential IDs reveal database size and creation order
3. **Predictability**: Users can guess valid IDs and attempt unauthorized access
4. **Privacy concerns**: IDs can correlate user activities across the application

### How to Use UUIDs

#### 1. Inherit from UuidMixin

All models that need to be referenced in URLs or frontend code must inherit from `UuidMixin`:

```python
from larpmanager.models.base import BaseModel, UuidMixin

class MyModel(UuidMixin, BaseModel):
    name = models.CharField(max_length=100)
    # ... other fields
```

**Note:** `UuidMixin` must come BEFORE `BaseModel` in the inheritance list.

#### 2. What UuidMixin Provides

The mixin automatically adds:
- A `uuid` field (12-character unique string)
- Automatic UUID generation on creation
- Database indexing for fast lookups
- Collision detection and retry logic

#### 3. Use UUID in URLs

**Bad - Using ID:**
```python
# urls.py
path('event/<int:event_id>/', views.event_detail, name='event_detail')

# views.py
def event_detail(request, event_id):
    event = Event.objects.get(id=event_id)  # WRONG!
```

**Good - Using UUID with ownership validation:**
```python
# urls.py
path('event/<str:event_uuid>/', views.event_detail, name='event_detail')

# views.py
from larpmanager.utils.core.common import get_element_event

def event_detail(request, context, event_uuid):
    # Automatically validates association/event ownership
    event = get_element_event(context, event_uuid, Event)
```

#### 4. Use UUID in Templates

**Bad - Using ID:**
```django
<a href="{% url 'event_detail' event.id %}">{{ event.name }}</a>
```

**Good - Using UUID:**
```django
<a href="{% url 'event_detail' event.uuid %}">{{ event.name }}</a>
```

#### 5. Always Validate Ownership

**CRITICAL:** Even with UUIDs, you must validate that objects belong to the correct association/event.

Use `get_element_event()` or `get_element()` - these functions automatically add ownership filters:

```python
# These functions automatically add filters like:
# - association_id=context['association_id'] (if model has 'association' field)
# - event=context['event'].get_class_parent(model_class) (if model has 'event' field)

from larpmanager.utils.core.common import get_element_event

obj = get_element_event(context, object_uuid, MyModel)
```

**Why this matters:**
- Without ownership validation, users could access objects from other organizations by guessing UUIDs
- UUIDs prevent enumeration, but don't prevent access to known/leaked UUIDs
- `get_element_event()` ensures proper multi-tenancy isolation

#### 6. Avoid IDs in Frontend Code

Do not use IDs in:
- HTML element IDs or data attributes
- JavaScript arrays or objects for processing
- Table row identifiers
- AJAX request parameters

**Bad - Using ID:**
```html
<tr id="row-{{ registration.id }}" data-reg-id="{{ registration.id }}">
    <td>{{ registration.name }}</td>
</tr>

<script>
const registrationIds = [
    {% for reg in registrations %}
        {{ reg.id }},
    {% endfor %}
];
</script>
```

**Good - Using UUID:**
```html
<tr id="row-{{ registration.uuid }}" data-reg-uuid="{{ registration.uuid }}">
    <td>{{ registration.name }}</td>
</tr>

<script>
const registrationUuids = [
    {% for reg in registrations %}
        "{{ reg.uuid }}",
    {% endfor %}
];
</script>
```

### Common Patterns

#### Get Object with Security Checks

**IMPORTANT:** Always use `get_element_event()` instead of Django's `get_object_or_404()`. This ensures proper association/event ownership validation.

```python
from larpmanager.utils.core.common import get_element_event

def my_view(request, context, object_uuid):
    # get_element_event automatically checks association_id and event ownership
    obj = get_element_event(context, object_uuid, MyModel)
```

**Why not use `get_object_or_404()`?**
- It doesn't validate association/event ownership
- Users could access objects from other organizations/events by guessing UUIDs
- `get_element_event()` automatically adds the necessary filters

**Alternative: Using get_element() for context-based views**
```python
from larpmanager.utils.core.common import get_element

def my_view(request, context, object_uuid):
    # Adds the object to context with automatic ownership validation
    get_element(context, object_uuid, 'my_object', MyModel)
    # Now available as context['my_object']
```

#### Form Actions
```django
<form method="post" action="{% url 'delete_item' item.uuid %}">
    {% csrf_token %}
    <button type="submit">Delete</button>
</form>
```

#### AJAX Requests
```javascript
// Bad
fetch(`/api/item/${itemId}/update`, { ... });

// Good
fetch(`/api/item/${itemUuid}/update`, { ... });
```

### When IDs Are Acceptable

Internal database operations where values are never exposed:
- Foreign key relationships in models
- Internal queries and filters
- Database migrations
- Admin panel (if restricted to superusers)

### Migration Guide

If you need to add UUIDs to an existing model:

1. Add `UuidMixin` to the model inheritance
2. Create and run migrations
3. Generate UUIDs for existing records (migration script)
4. Update all views to use `uuid` instead of `id`
5. Update all URL patterns to accept UUID parameters
6. Update all templates to use UUIDs
7. Test thoroughly

---

## SQL Injection Prevention

Always use Django ORM properly to prevent SQL injection:

**Bad:**
```python
# NEVER do this
query = f"SELECT * FROM app_model WHERE name = '{user_input}'"
Model.objects.raw(query)
```

**Good:**
```python
# Use ORM filters
Model.objects.filter(name=user_input)

# Or use parameterized queries
Model.objects.raw("SELECT * FROM app_model WHERE name = %s", [user_input])
```

---

## XSS Prevention

1. **Always escape user input** in templates (Django does this by default)
2. **Use `|safe` filter only for trusted content**
3. **Sanitize HTML** when using TinyMCE or accepting rich text
4. **Validate and escape** data in JavaScript

**Bad:**
```django
{{ user_input|safe }}  {# DANGEROUS if user_input is not sanitized #}
```

**Good:**
```django
{{ user_input }}  {# Automatically escaped #}

{# Or for trusted HTML from TinyMCE #}
{{ trusted_html_field|safe }}  {# Only if the field is properly sanitized #}
```

---

## CSRF Protection

1. **Always include `{% csrf_token %}`** in forms
2. **Use Django's CSRF middleware** (enabled by default)
3. **For AJAX requests**, include CSRF token in headers

```javascript
// Get CSRF token from cookie
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

// Include in fetch requests
fetch('/api/endpoint/', {
    method: 'POST',
    headers: {
        'X-CSRFToken': getCookie('csrftoken'),
        'Content-Type': 'application/json',
    },
    body: JSON.stringify(data)
});
```

---

## Security Checklist

Before submitting any code, verify:

- [ ] No direct IDs in URLs (use UUIDs)
- [ ] No IDs in HTML attributes or JavaScript code
- [ ] All models with URL exposure inherit from `UuidMixin`
- [ ] Using `get_element_event()` or `get_element()` instead of `get_object_or_404()` for ownership validation
- [ ] All user input is properly escaped
- [ ] No raw SQL queries with string interpolation
- [ ] CSRF tokens included in all forms
- [ ] No sensitive data logged or exposed in error messages
- [ ] File uploads are validated and sanitized
- [ ] Authentication and permission checks on all views
