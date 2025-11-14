# Request Attributes & Context - Quick Reference Guide

## TL;DR: The Pattern

```python
# MIDDLEWARE (sets these)
request.association = {id, name, slug, skin_id, main_domain, footer, logo, ...}
request.enviro = "prod" | "staging" | "dev" | "test"

# CONTEXT BUILDER (copies these)
context = get_context(request)  # Copies ALL request.association into context + member/membership/features/etc

# IN VIEWS/TEMPLATES
# Before get_context(): Use request.association["id"]
# After get_context(): Use context["association_id"] (better!)
```

---

## 1. What Gets Added Where

### Middleware Sets (Always Available)
- **File:** `/home/user/larpmanager/larpmanager/middleware/association.py:192`
- **What:** `request.association`, `request.enviro`
- **Safety:** 100% guaranteed by middleware chain

### Context Builders Create
- **File:** `/home/user/larpmanager/larpmanager/utils/base.py`
- **Functions:**
  - `get_context(request)` - Base context
  - `check_association_context(request, perm)` - With permissions check
  - `get_event_context(request, slug)` - With event/run data
  - `check_event_context(request, slug, perm)` - With permissions check

---

## 2. Quick Context Keys Reference

### Association Level (from get_context)
```
association_id, id, name, slug, skin_id, main_domain, footer, 
platform, logo, skin_managed, features, token_name, credit_name
```

### User/Member Level (from get_context)
```
member, membership, is_staff, interface_collapse_sidebar
```

### Management Flags (from check_*_context)
```
manage, exe_page, orga_page, is_sidebar_open, tutorial, config
```

### Event/Run Level (from get_event_context)
```
run, event, features, staff, skip, association_slug
```

### UI/Config (from get_context)
```
TINYMCE_DEFAULT_CONFIG, TINYMCE_JS_URL, request_func_name
```

---

## 3. Common Access Patterns

### Pattern A: Early Dispatch (ACCEPTABLE)
```python
def manage(request, event_slug=None):
    if request.association["id"] == 0:  # OK - early exit before context
        return redirect("home")
    if event_slug:
        return _orga_manage(request, event_slug)
    return _exe_manage(request)
```

### Pattern B: Full View (PREFERRED)
```python
def my_view(request, event_slug):
    context = check_event_context(request, event_slug, "some_permission")
    
    # Now use context instead
    association_id = context["association_id"]  # NOT request.association["id"]
    event = context["event"]
    run = context["run"]
    
    return render(request, "template.html", context)
```

### Pattern C: AJAX (ACCEPTABLE)
```python
@csrf_exempt
def upload_media(request):
    if request.method == "POST":
        # Middleware guarantees this exists
        association_id = request.association['id']
        # Direct access OK for simple endpoints
        ...
```

### Pattern D: WRONG (DON'T DO THIS)
```python
def bad_view(request):
    context = get_context(request)  # Built context!
    
    # Then access request instead of context
    assoc_name = request.association["name"]  # WRONG!
    
    # Should be:
    assoc_name = context["name"]  # CORRECT!
```

---

## 4. Direct `request.association` Usages (Current State)

| File | Line | Purpose | OK? |
|------|------|---------|-----|
| views/manage.py | 67 | Dispatch routing | ✓ Early exit |
| views/auth.py | 80 | CBV form setup | ✗ Should use context |
| views/base.py | 99 | Home routing | ✓ Early exit |
| views/base.py | 223 | Upload path | ✓ AJAX endpoint |
| views/larpmanager.py | 575-610 | Join form | ✗ Should refactor |
| views/orga/event.py | 227 | Event fetch | ✗ Should use context |
| views/api.py | 163 | API check | ✓ Defensive check |
| middleware/exception.py | 97 | Error handler | ✓ Middleware context |

**Legend:** 
- ✓ = Acceptable use (early exit, AJAX, middleware)
- ✗ = Should refactor (after context built)

---

## 5. `request.user.member` Usage

This is **different** from `request.association`:
- **NOT set by middleware** - it's a Django user extension
- Used **extensively** in views and templates
- Also available as `context["member"]`
- Both patterns are common and acceptable

```python
# Direct access (common)
if request.user.member.parent:
    login(request, request.user.member.parent, backend=backend)

# Context access (alternative)
if context.get("member") and context["member"].parent:
    ...
```

---

## 6. Template Usage

### Good (Preferred)
```html
{{ association.logo }}
{{ association.footer | safe }}
{{ association.name }}
{{ member.name }}
{{ run.id }}
{{ event.name }}
```

### OK (Standard Django)
```html
{{ request.path }}
{{ request.GET.next }}
{{ request.user.member.parent }}
{{ request.enviro }}
```

### Avoid
```html
{{ request.association["id"] }}  <!-- Don't use in templates -->
```

---

## 7. Refactoring Checklist

When refactoring request attribute access:

- [ ] View calls `get_context()` or similar → Use context keys after
- [ ] View does early dispatch check → Direct request access OK
- [ ] View is AJAX/JSON endpoint → Direct request access OK  
- [ ] Template uses association data → Use context variable
- [ ] Template uses member/user info → Can use request or context
- [ ] Exception handler → Direct request access OK

---

## 8. File Structure Quick Map

```
middleware/
├── association.py       ← SETS request.association (line 192)
├── exception.py         ← USES request.association (line 97)
└── token.py             ← Handles auth tokens

utils/
└── base.py
    ├── get_context()                    (line 55)
    ├── check_association_context()      (line 169)
    ├── check_event_context()            (line 225)
    ├── get_event_context()              (line 333)
    └── get_run()                        (line 439)

views/
├── base.py              ← auth views with request.association access
├── auth.py              ← login/after_login, uses request.association
├── manage.py            ← dispatcher, early exit OK
├── larpmanager.py       ← home pages, JOIN FORM needs refactoring (575-610)
├── api.py               ← API endpoint, defensive access OK
└── orga/
    └── event.py         ← Event mgmt, line 227 should use context

templates/
└── *.html               ← Mostly use context variables (good!)
    └── structure.html   ← Uses request.enviro (OK)
    └── member/*.html    ← Uses request.user.member (OK)
```

---

## 9. Copy-Paste Refactoring Examples

### Example 1: Before → After (home() view)

**BEFORE:**
```python
def home(request: HttpRequest, lang: str | None = None) -> HttpResponse:
    if request.association["id"] == 0:
        return lm_home(request)
    context = get_context(request)
    return check_centauri(request, context) or calendar(request, context, lang)
```

**AFTER:**
```python
def home(request: HttpRequest, lang: str | None = None) -> HttpResponse:
    context = get_context(request)
    if context["association_id"] == 0:
        return lm_home(request)
    return check_centauri(request, context) or calendar(request, context, lang)
```

### Example 2: Before → After (orga_event view)

**BEFORE:**
```python
def orga_event(request: HttpRequest, event_slug: str) -> HttpResponse:
    context = check_event_context(request, event_slug, "orga_event")
    # Later in the code:
    run = get_cache_run(request.association["id"], event_slug)  # ← WRONG!
    return full_event_edit(context, request, context["event"], context["run"])
```

**AFTER:**
```python
def orga_event(request: HttpRequest, event_slug: str) -> HttpResponse:
    context = check_event_context(request, event_slug, "orga_event")
    # run is already in context!
    return full_event_edit(context, request, context["event"], context["run"])
```

---

## 10. Key Takeaways

1. **Middleware is the SOURCE** - `request.association` created here, safe to use anywhere
2. **Context COPIES everything** - After `get_context()`, data is in `context` dict
3. **Use context when available** - Cleaner, more testable, explicit
4. **Early-exit checks are OK** - Dispatch routing before context is acceptable
5. **AJAX endpoints are OK** - Simple endpoints can use request directly
6. **Templates prefer context** - But `request.path`, `request.user`, `request.enviro` are standard Django
7. **`request.user.member` is different** - Django extension, not middleware-set

