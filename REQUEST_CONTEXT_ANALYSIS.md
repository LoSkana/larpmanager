# Request Attributes vs Context Analysis - LarpManager Django Codebase

## Executive Summary

This codebase shows a clear pattern of:
1. **Middleware adding attributes to request** (primarily `request.association`)
2. **Context builders copying request attributes** into context dictionaries
3. **Direct request attribute access** persisting in views and middleware exception handlers
4. **Template access** primarily through context variables (preferred) with some direct request usage

The main opportunity for refactoring is to **eliminate direct `request.association` access outside of middleware** and use context instead.

---

## 1. MIDDLEWARE: Request Attributes Being Added

### 1.1 Association Middleware (`/home/user/larpmanager/larpmanager/middleware/association.py`)

**Sets these request attributes:**

```python
# Line 88-96: request.enviro
request.enviro = "prod"      # or "staging", "dev", "test"

# Line 192: request.association (dict)
request.association = association_data
# Contains: id, name, slug, skin_id, main_domain, footer, logo, etc.

# Line 198-202: request.association["footer"] (added)
request.association["footer"] = get_association_text(...)
```

**File:** `/home/user/larpmanager/larpmanager/middleware/association.py:172-203`

This is the PRIMARY place where custom request attributes are set. The association data is loaded from cache as a dictionary.

### 1.2 Token Auth Middleware (`/home/user/larpmanager/larpmanager/middleware/token.py`)

Doesn't add request attributes directly, but enables login via token authentication.

---

## 2. CONTEXT BUILDERS: Copying Request Attributes to Context

### 2.1 Main Context Builder: `get_context()` 

**File:** `/home/user/larpmanager/larpmanager/utils/base.py:55-135`

This is the PRIMARY context builder. It does the following:

```python
def get_context(request: HttpRequest, *, check_main_site: bool = False) -> dict:
    """
    Builds comprehensive context from request.
    """
    # Line 81: Copy association_id
    context = {"association_id": request.association["id"]}
    
    # Line 84-85: Copy ALL request.association keys to context
    for association_key in request.association:
        context[association_key] = request.association[association_key]
    
    # Line 88-91: Add member from request
    context["member"] = None
    context["membership"] = None
    if hasattr(request, "user") and hasattr(request.user, "member"):
        context["member"] = request.user.member
    
    # Line 109: Get membership info
    context["membership"] = get_user_membership(context["member"], context["association_id"])
    
    # Line 112: Get association permissions
    get_index_association_permissions(context, request, context["association_id"], enforce_check=False)
    
    # Line 115-117: Add UI preferences
    context["interface_collapse_sidebar"] = context["member"].get_config(...)
    context["is_staff"] = request.user.is_staff
    
    # Line 128-129: Add TinyMCE config
    context["TINYMCE_DEFAULT_CONFIG"] = conf_settings.TINYMCE_DEFAULT_CONFIG
    context["TINYMCE_JS_URL"] = conf_settings.TINYMCE_JS_URL
    
    # Line 133: Add request function name
    context["request_func_name"] = request.resolver_match.func.__name__
    
    return context
```

**Result:** Context now contains ALL association data plus member, membership, features, etc.

### 2.2 Association Context: `check_association_context()`

**File:** `/home/user/larpmanager/larpmanager/utils/base.py:169-222`

Wraps `get_context()` and adds:
- Permission checking
- Management flags: `context["manage"] = 1`, `context["exe_page"] = 1`
- Sidebar state: `context["is_sidebar_open"]`
- Tutorial info
- Config URL

### 2.3 Event Context Builders: `get_event_context()` and `check_event_context()`

**File:** `/home/user/larpmanager/larpmanager/utils/base.py:333-402`

Extends base context with:
- `context["run"]` - Run object
- `context["event"]` - Event object
- `context["features"]` - Event features
- `context["staff"]`, `context["skip"]`
- `context["orga_page"] = 1`
- Run configuration and writing fields

---

## 3. COMMON REQUEST ATTRIBUTE ACCESSES (Direct Access to request)

### 3.1 Direct `request.association` Access

**These occur OUTSIDE of context building and should be refactored:**

| Location | Line | Pattern | Issue |
|----------|------|---------|-------|
| `/home/user/larpmanager/larpmanager/views/manage.py` | 67 | `request.association["id"]` | Should use context after `get_context()` |
| `/home/user/larpmanager/larpmanager/views/auth.py` | 79-80 | `self.request.association["id"]` | In a CBV form - should have context |
| `/home/user/larpmanager/larpmanager/views/base.py` | 99 | `request.association["id"]` | Checked early in home() view |
| `/home/user/larpmanager/larpmanager/views/base.py` | 223 | `request.association['id']` | In upload_media() - direct access |
| `/home/user/larpmanager/larpmanager/views/larpmanager.py` | 575 | `request.association["name"]` | Direct access in join() view |
| `/home/user/larpmanager/larpmanager/views/larpmanager.py` | 577 | `request.association["skin_id"]` | Direct access in _join_form() |
| `/home/user/larpmanager/larpmanager/views/larpmanager.py` | 610 | `request.association["skin_id"]` | Direct access when creating association |
| `/home/user/larpmanager/larpmanager/views/larpmanager.py` | 1163 | `request.association["skin_id"]` | Direct access in another location |
| `/home/user/larpmanager/larpmanager/views/api.py` | 163 | `request.association.get("id", 0)` | Defensive access in API |
| `/home/user/larpmanager/larpmanager/views/orga/event.py` | 227 | `request.association["id"]` | Direct access in orga_event() |
| `/home/user/larpmanager/larpmanager/middleware/exception.py` | 97 | `request.association["id"]` | In exception handler middleware |

### 3.2 Direct `request.user.member` Access

These are **VERY COMMON** and harder to refactor (extensive use):

```python
# /home/user/larpmanager/larpmanager/views/auth.py:80
get_user_membership(self.request.user.member, self.request.association["id"])

# /home/user/larpmanager/larpmanager/views/base.py:273
save_single_config(request.user.member, config_name, value)

# /home/user/larpmanager/larpmanager/views/user/member.py (MANY LINES)
request.user.member.id
request.user.member.language
request.user.member.profile
request.user.member.parent
# ... and many more
```

### 3.3 Direct `request.enviro` Access

Minimal usage:

```python
# /home/user/larpmanager/larpmanager/templates/structure.html:139
window.enviro = "{{ request.enviro }}";
```

---

## 4. CONTEXT KEYS COMMONLY SET AND USED

After calling `get_context()` or similar, these keys are available in context:

### 4.1 Association-Level Keys
```python
context["association_id"]          # Primary key
context["id"]                      # Same as association_id (from request.association)
context["name"]                    # Association name
context["slug"]                    # Association slug
context["skin_id"]                 # Skin identifier
context["main_domain"]             # Main domain
context["footer"]                  # Localized footer text
context["platform"]                # Platform name
context["logo"]                    # Logo URL
context["skin_managed"]            # Boolean
context["features"]                # Dict of association features
```

### 4.2 User/Member Keys
```python
context["member"]                  # Member object or None
context["membership"]              # Membership object
context["is_staff"]                # Boolean
context["interface_collapse_sidebar"]  # Boolean (user preference)
```

### 4.3 Management/Page Type Keys
```python
context["manage"]                  # 1 (flag for management pages)
context["exe_page"]                # 1 (executive/organization-wide page)
context["orga_page"]               # 1 (event/organizer page)
context["is_sidebar_open"]         # Boolean
```

### 4.4 Event-Level Keys (when using get_event_context)
```python
context["run"]                     # Run object
context["event"]                   # Event object
context["features"]                # Event features dict
context["staff"]                   # "1" if user is staff
context["skip"]                    # "1" if should skip
context["association_slug"]        # From request or event
```

### 4.5 UI/Config Keys
```python
context["TINYMCE_DEFAULT_CONFIG"]  # TinyMCE settings
context["TINYMCE_JS_URL"]          # TinyMCE JS URL
context["request_func_name"]       # Current view function name
context["tutorial"]                # Tutorial identifier
context["config"]                  # Config URL if applicable
```

---

## 5. TEMPLATE USAGE PATTERNS

### 5.1 Request Attributes Used in Templates

**Mostly for form paths and basic request info:**

```html
<!-- /home/user/larpmanager/larpmanager/templates/structure.html:139 -->
window.enviro = "{{ request.enviro }}";

<!-- /home/user/larpmanager/larpmanager/templates/larpmanager/member/delegated.html:7,12 -->
{% if request.user.member.parent %}
    You are currently logged in with: <b>{{ request.user.member }}</b>

<!-- /home/user/larpmanager/larpmanager/templates/larpmanager/event/character.html:8 -->
{% if char.player_id == request.user.member.id %}

<!-- Multiple templates for form submission -->
<form action="{{ request.path }}" method="post">
```

### 5.2 Context Variables Used in Templates

**Preferred approach - used much more than request access:**

```html
<!-- Association data -->
<img src="{{ association.logo }}" class="main_logo" alt="logo" />
{{ association.footer | safe }}
{{ association.platform }}
{{ association.name }}

<!-- Event/Run data -->
<table id="writing_list_{{ run.id }}_{{ typ }}">
{{ event.association }} - {{ event }}

<!-- Member data -->
Hi {{ member.name }},
```

---

## 6. DETAILED EXAMPLES OF REFACTORING OPPORTUNITIES

### 6.1 Example 1: `home()` view in auth.py

**Current Code (Direct request access):**
```python
# /home/user/larpmanager/larpmanager/views/auth.py:99-104
def home(request: HttpRequest, lang: str | None = None) -> HttpResponse:
    # Check if this is the default/main association (ID 0)
    if request.association["id"] == 0:
        return lm_home(request)
    
    # For other associations, check Centauri handling or fallback to calendar
    context = get_context(request)
    return check_centauri(request, context) or calendar(request, context, lang)
```

**Issue:** 
- Accesses `request.association["id"]` BEFORE calling `get_context()`
- After getting context, association_id is available as `context["association_id"]`

**Refactored:**
```python
def home(request: HttpRequest, lang: str | None = None) -> HttpResponse:
    context = get_context(request)
    
    # Check if this is the default/main association (ID 0)
    if context["association_id"] == 0:
        return lm_home(request)
    
    # For other associations, check Centauri handling or fallback to calendar
    return check_centauri(request, context) or calendar(request, context, lang)
```

---

### 6.2 Example 2: `upload_media()` in base.py

**Current Code:**
```python
# /home/user/larpmanager/larpmanager/views/base.py:205-226
@csrf_exempt
def upload_media(request: HttpRequest) -> JsonResponse:
    if request.method == "POST" and request.FILES.get("file"):
        file = request.FILES["file"]
        timestamp = timezone.now().strftime("%Y%m%d%H%M%S")
        filename = f"{timestamp}_{uuid.uuid4().hex}{file.name[file.name.rfind('.') :]}"
        
        # Direct request.association access
        path = default_storage.save(f"tinymce_uploads/{request.association['id']}/{filename}", file)
        
        return JsonResponse({"location": default_storage.url(path)})
    return JsonResponse({"error": "Invalid request"}, status=400)
```

**Issue:**
- AJAX endpoint that doesn't use get_context() pattern
- Could pass association_id via the request context or as a separate parameter

**Refactored:**
```python
@csrf_exempt
def upload_media(request: HttpRequest) -> JsonResponse:
    if request.method == "POST" and request.FILES.get("file"):
        file = request.FILES["file"]
        timestamp = timezone.now().strftime("%Y%m%d%H%M%S")
        filename = f"{timestamp}_{uuid.uuid4().hex}{file.name[file.name.rfind('.') :]}"
        
        # Get association_id from properly initialized request.association
        # (set by middleware, so safe to use)
        association_id = request.association.get('id', 0)
        if association_id == 0:
            return JsonResponse({"error": "Invalid association"}, status=400)
        
        path = default_storage.save(f"tinymce_uploads/{association_id}/{filename}", file)
        
        return JsonResponse({"location": default_storage.url(path)})
    return JsonResponse({"error": "Invalid request"}, status=400)
```

---

### 6.3 Example 3: `manage()` in manage.py

**Current Code:**
```python
# /home/user/larpmanager/larpmanager/views/manage.py:52-72
@login_required
def manage(request: HttpRequest, event_slug=None):
    if request.association["id"] == 0:
        return redirect("home")
    
    if event_slug:
        return _orga_manage(request, event_slug)
    return _exe_manage(request)
```

**Issue:**
- Direct request.association access for early check
- Could be moved to after context creation if needed

**Observation:**
- This is actually a dispatcher/router view, so early check is reasonable
- The real issue is when association["id"] is checked in views that THEN call get_context()

---

### 6.4 Example 4: Exception Middleware

**File:** `/home/user/larpmanager/larpmanager/middleware/exception.py:97`

```python
"runs": Run.objects.filter(development=DevelopStatus.SHOW)
    .exclude(event__visible=False)
    .select_related("event")
    .filter(event__association_id=request.association["id"])  # <- Direct access
    .order_by("-end"),
```

**Context:**
- This is in an exception handler, so context building might be incomplete
- Direct request.association access is appropriate here (already set by middleware)

---

## 7. MIDDLEWARE RESPONSIBILITY

### 7.1 What Middleware Sets (AssociationIdentifyMiddleware)

**Guaranteed to be set by line 192-202:**
- `request.association` - dictionary with association data
- `request.association["footer"]` - localized footer text
- `request.enviro` - environment type

**These are safe to use anywhere after middleware processing** because they're set very early in the request cycle.

---

## 8. KEY FINDINGS & OPPORTUNITIES

### Finding 1: Inconsistent Access Pattern
- **Before** `get_context()` is called: Must use `request.association`
- **After** `get_context()` is called: Should use `context["association_id"]` etc.
- **Current Issue:** Code mixes these patterns inconsistently

### Finding 2: Context Builder Copies Everything
The `get_context()` function copies ALL keys from `request.association` to context:
```python
for association_key in request.association:
    context[association_key] = request.association[association_key]
```

This means after calling `get_context()`, you have:
- `context["id"]`
- `context["name"]`
- `context["slug"]`
- `context["skin_id"]`
- etc.

### Finding 3: Template Consistency
- Templates **mostly use context variables** (preferred)
- Only uses `request.` for:
  - `request.path` - form actions
  - `request.GET.next` - form redirects
  - `request.enviro` - JavaScript environment
  - `request.user.member` - member-specific info

### Finding 4: `request.user.member` is Different
- `request.user.member` is **NOT set by middleware**
- It's a Django user extension (custom Member model)
- This is accessed in context as `context["member"]`
- Both patterns are used in templates and views

---

## 9. REFACTORING RECOMMENDATIONS

### Priority 1: Early-Exit Views
Views that check `request.association["id"] == 0` at the start for routing decisions are acceptable because:
- The check happens before context creation
- It's used for early exit/dispatch logic

**Examples:** `manage()`, `home()`

### Priority 2: AJAX Endpoints
AJAX endpoints like `upload_media()` and `set_member_config()` that access `request.association` are acceptable because:
- Middleware guarantees `request.association` is set
- These are endpoint-specific views
- They don't need full context

### Priority 3: Main View Logic
Views that call `get_context()` but then also access `request.association` directly should be refactored:
- After calling `get_context()`, use `context` keys instead
- Makes intent clearer and reduces coupling to request structure

**Examples to Refactor:**
- `/home/user/larpmanager/larpmanager/views/larpmanager.py:575-610` - _join_form()
- Any view accessing both `request.association` and `context`

### Priority 4: Template Cleanup
Templates are mostly good, but could:
- Prefer `{{ association.* }}` over `{{ request.association.* }}`
- Keep `request.path` and `request.user.member` as they are (standard Django)

---

## 10. SUMMARY TABLE: Where to Use What

| Context | Use `request.association` | Use `context` | Notes |
|---------|--------------------------|-------------|-------|
| Middleware | YES | NO | Sets the values |
| Exception handlers | YES | Sometimes | Might not have context |
| View - before get_context() | YES | NO | Context not built yet |
| View - after get_context() | NO | YES | Preferred pattern |
| AJAX/JSON endpoints | YES | Maybe | Depends on complexity |
| Template | Sometimes | YES | Prefer context |
| CBV methods | YES* | YES* | Depends on method stage |

*For CBV, check when context is built (form_valid vs get_context)

---

## 11. FILES ANALYZED

### Middleware
- `/home/user/larpmanager/larpmanager/middleware/association.py` - SETS request.association
- `/home/user/larpmanager/larpmanager/middleware/exception.py` - USES request.association

### Utilities
- `/home/user/larpmanager/larpmanager/utils/base.py` - BUILDS context

### Views (Key Examples)
- `/home/user/larpmanager/larpmanager/views/base.py` - auth views
- `/home/user/larpmanager/larpmanager/views/auth.py` - login
- `/home/user/larpmanager/larpmanager/views/manage.py` - dispatcher
- `/home/user/larpmanager/larpmanager/views/larpmanager.py` - home pages
- `/home/user/larpmanager/larpmanager/views/orga/event.py` - event management

### Templates
- Multiple `.html` files in `/home/user/larpmanager/larpmanager/templates/`

