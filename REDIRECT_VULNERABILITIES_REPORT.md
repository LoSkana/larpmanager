# Open Redirect and URL Manipulation Vulnerability Report
## LarpManager Security Audit

**Date:** 2025-11-21  
**Severity Level:** CRITICAL to MEDIUM  
**Total Vulnerabilities Found:** 8 Major Issues

---

## CRITICAL VULNERABILITIES

### 1. Path Traversal in Feature Activation (CRITICAL)
**File:** `/home/user/larpmanager/larpmanager/views/larpmanager.py`  
**Lines:** 335-336, 395-396  
**Severity:** CRITICAL  

**Vulnerable Code:**
```python
# Line 335-336 (activate_feature_association)
if path:
    return redirect("/" + path)  # VULNERABLE: Unvalidated path parameter

# Line 395-396 (activate_feature_event)  
if path:
    return redirect("/" + path)  # VULNERABLE: Unvalidated path parameter
```

**URL Pattern:**
```python
path("activate/<slug:feature_slug>/next/<path:path>",
     views_lm.activate_feature_association,
     name="activate_feature_assoc"),

path("<slug:event_slug>/activate/<slug:feature_slug>/next/<path:path>",
     views_lm.activate_feature_event,
     name="activate_feature_event"),
```

**Exploitation Example:**
```
GET /activate/feature-slug/next/https://evil.com/
GET /event-slug/activate/feature-slug/next/https://attacker.com/
```
After activation, user is redirected to: `https://evil.com/` or `https://attacker.com/`

**Impact:** Attackers can redirect users to malicious sites after feature activation
**Fix:** Use Django's `url_has_allowed_host_and_scheme()` to validate the path parameter

---

### 2. Payment Redirect with User-Controlled Path (CRITICAL)
**File:** `/home/user/larpmanager/larpmanager/views/user/accounting.py`  
**Lines:** 977, 984  
**Severity:** CRITICAL  

**Vulnerable Code:**
```python
# Line 977
if not form.is_valid():
    messages.error(request, mes)
    return redirect("/" + redirect_path)  # VULNERABLE: redirect_path is user-controlled

# Line 984
except ObjectDoesNotExist:
    messages.error(request, _("Error processing payment, contact us"))
    return redirect("/" + redirect_path)  # VULNERABLE: redirect_path is user-controlled
```

**URL Pattern:**
```python
path("accounting/submit/<slug:payment_method>/<path:redirect_path>/",
     views_ua.acc_submit,
     name="acc_submit"),
```

**Exploitation Example:**
```
POST /accounting/submit/wire/https://malicious-site.com/phishing/
POST /accounting/submit/paypal_nf/javascript:alert('xss')/
POST /accounting/submit/any/../../../etc/passwd/
```

**Impact:** Users redirected to malicious sites during payment flow, phishing attacks
**Fix:** Validate redirect_path with `url_has_allowed_host_and_scheme()`

---

### 3. Arbitrary Subdomain and Path Concatenation (CRITICAL)
**File:** `/home/user/larpmanager/larpmanager/views/larpmanager.py`  
**Lines:** 161-166  
**Severity:** CRITICAL  

**Vulnerable Code:**
```python
def go_redirect(request: HttpRequest, slug: Any, path: Any, 
                base_domain: Any = "larpmanager.com") -> Any:
    if request.enviro in ["dev", "test"]:
        return redirect("http://127.0.0.1:8000/")

    new_path = f"https://{slug}.{base_domain}/" if slug else f"https://{base_domain}/"
    
    if path:
        new_path += path  # VULNERABLE: Path concatenation without validation
    
    return redirect(new_path)
```

**Usage Locations:**
- Line 184: `go_redirect(request, association_slugs[0], redirect_path)`
- Line 191: `go_redirect(request, association_slugs[selected_index], redirect_path)`
- Line 213: `full_url = f"https://{run.event.association.slug}.{run.event.association.skin.domain}/{run.get_slug()}/{path}"`

**Exploitation Example:**
```
POST /redirect/event/
Form submission with redirect_path: "javascript:alert('xss')"
Result: redirect to https://<slug>.larpmanager.com/javascript:alert('xss')

GET /redr/https://google.com/
Bypasses slug validation and performs redirect
```

**Impact:** Open redirect to arbitrary domains, potential phishing and malware distribution
**Fix:** Validate path parameter and use relative URLs or reverse() for safe redirects

---

## HIGH SEVERITY VULNERABILITIES

### 4. Template Path Parameter Injection (HIGH)
**File:** `/home/user/larpmanager/larpmanager/templates/elements/payment_go.html`  
**Lines:** 103, 131, 207  
**Severity:** HIGH  

**Vulnerable Code:**
```django
<form action="{% url 'acc_submit' 'any' request.path %}" method="post">
<form action="{% url 'acc_submit' 'wire' request.path %}" method="post">
<form action="{% url 'acc_submit' 'paypal_nf' request.path %}" method="post">
```

**Issue:** `request.path` contains user-controlled data and is passed to URL pattern  

**Exploitation Example:**
```
GET /accounting/payment/https%3A%2F%2Fevil.com/
The request.path would be passed as redirect_path parameter
```

**Impact:** Combines with vulnerability #2 to create direct redirect chains
**Fix:** Generate redirect paths server-side or validate in view

---

### 5. Next Parameter in Login Template (MEDIUM/HIGH)
**File:** `/home/user/larpmanager/larpmanager/templates/registration/login.html`  
**Line:** 49  
**Severity:** MEDIUM/HIGH  

**Vulnerable Code:**
```django
<a href="{% url 'registration_register' %}?next={{ request.GET.next|urlencode }}">
    {% trans "Register" %}
</a>
```

**Issue:** `request.GET.next` passed to template without validation

**Exploitation Example:**
```
GET /login/?next=https://attacker.com/
Link to registration will be: /register/?next=https://attacker.com/
If registration view uses this next parameter, redirect will occur
```

**Impact:** Phishing attacks through registration flow
**Fix:** Validate next parameter in view using `url_has_allowed_host_and_scheme()`

---

## MEDIUM SEVERITY VULNERABILITIES

### 6. Path Reconstruction in Middleware (MEDIUM)
**File:** `/home/user/larpmanager/larpmanager/middleware/broken.py`  
**Lines:** 105-108  
**Severity:** MEDIUM  

**Vulnerable Code:**
```python
# Handle domain redirection for larpmanager.com with $ separator
if domain == "larpmanager.com" and "$" in path:
    path_parts = path.split("$")
    url = "https://" + path_parts[1] + ".larpmanager.com/" + path_parts[0]
    return HttpResponseRedirect(url)
```

**Exploitation Example:**
```
GET /path$attacker.com/
Result: Redirect to https://attacker.com/path/

GET /evil.com/$admin/
Result: Redirect to https://admin/evil.com/
```

**Impact:** Open redirect through undocumented mechanism
**Fix:** Remove or validate this path separator logic

---

### 7. Subdomain Redirect Without Validation (MEDIUM)
**File:** `/home/user/larpmanager/larpmanager/middleware/association.py`  
**Lines:** 122, 166  
**Severity:** MEDIUM  

**Vulnerable Code:**
```python
# Line 122
return redirect(f"https://{association_slug}.{association_domain}{request.get_full_path()}")

# Line 166  
return redirect(f"https://larpmanager.com{request.get_full_path()}")
```

**Issue:** `request.get_full_path()` might contain user-controlled query parameters

**Exploitation Example:**
```
GET /path?next=javascript:alert('xss')
Preserves next parameter in redirect
```

**Impact:** Parameter preservation in redirects, potential secondary vulnerabilities
**Fix:** Filter request path before including in redirect

---

### 8. Auto-Save JavaScript Redirect (MEDIUM)
**File:** `/home/user/larpmanager/larpmanager/templates/elements/auto-save.js`  
**Lines:** 158-162  
**Severity:** MEDIUM  

**Vulnerable Code:**
```javascript
$('.trigger_save').on('click', function(e) {
    e.preventDefault();
    var href = $(this).attr('href');  // User-controlled href
    submitForm(false)
        .then(function() {
            window.location.href = href;  // VULNERABLE: Client-side redirect
        });
});
```

**Exploitation Example:**
```html
<a href="javascript:alert('xss')" class="trigger_save">Save and Continue</a>
<a href="https://attacker.com/" class="trigger_save">Save</a>
```

**Impact:** Client-side open redirect, JavaScript execution
**Fix:** Validate href before assignment, use URL.parse() and whitelist domains

---

## POSITIVE FINDINGS

### Secure Implementation Found:
**File:** `/home/user/larpmanager/larpmanager/views/auth.py`  
**Lines:** 109-113  
**Status:** SECURE  

```python
def get_success_url(self, user: Member | None = None) -> str:
    next_url = self.request.POST.get("next") or self.request.GET.get("next")
    
    # SECURE: Uses Django's url_has_allowed_host_and_scheme()
    if next_url and url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={self.request.get_host()}
    ):
        return next_url
    
    return self.success_url or reverse("home")
```

This is the correct approach - use Django's built-in security functions!

---

## REMEDIATION SUMMARY

### Recommended Fixes (Priority Order):

1. **IMMEDIATE (CRITICAL):**
   - Replace line 336 & 396 in `larpmanager.py`: 
     ```python
     if path and url_has_allowed_host_and_scheme(path, allowed_hosts={request.get_host()}):
         return redirect(path)
     return redirect("dashboard")
     ```

   - Replace lines 977, 984 in `accounting.py`:
     ```python
     if redirect_path and url_has_allowed_host_and_scheme(
         "/" + redirect_path, allowed_hosts={request.get_host()}
     ):
         return redirect("/" + redirect_path)
     return redirect("home")
     ```

   - Fix `go_redirect()` function to validate paths and use relative URLs

2. **HIGH PRIORITY:**
   - Validate `request.path` before using in templates
   - Implement server-side redirect path generation

3. **MEDIUM PRIORITY:**
   - Remove path separator logic from `broken.py` middleware
   - Sanitize JavaScript href attributes
   - Filter query parameters in middleware redirects

### Testing Recommendations:

1. Add unit tests for all redirect functions with malicious payloads:
   ```python
   def test_activate_feature_open_redirect():
       response = client.get('/activate/feature/next/https://evil.com/')
       assert response.status_code == 302
       assert 'evil.com' not in response['Location']
   ```

2. Implement request path validation tests

3. Use Django's test client to verify redirect destinations

---

## Compliance Notes

- **OWASP Top 10:** A01:2021 - Broken Access Control (Open Redirects)
- **CWE-601:** URL Redirection to Untrusted Site ('Open Redirect')
- **Django Security:** Follow Django's `url_has_allowed_host_and_scheme()` pattern
- **SANS Top 25:** CWE-601 (Open Redirect)

