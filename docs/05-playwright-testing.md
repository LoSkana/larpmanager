# Developer Guide: Playwright Testing

This guide explains how to write and run end-to-end (E2E) tests using Playwright in LarpManager.

**Related guides:**
- [Features and Permissions Guide](01-features-and-permissions.md) - Understand features before testing them
- [Configuration System Guide](03-configuration-system.md) - Test configuration options

---

## Table of Contents

1. [Overview](#overview)
2. [Test Structure](#test-structure)
3. [Writing Your First Test](#writing-your-first-test)
4. [Helper Functions](#helper-functions)
5. [Recording Tests](#recording-tests)
6. [Running Tests](#running-tests)
7. [Best Practices](#best-practices)
8. [Common Patterns](#common-patterns)
9. [Troubleshooting](#troubleshooting)

---

## Overview

### What are Playwright Tests?

Playwright tests are **end-to-end (E2E) tests** that simulate real user interactions with the application in a browser. Unlike unit tests that test individual functions, Playwright tests:

- Open a real browser (Chrome/Firefox/Safari)
- Navigate through the application like a user would
- Click buttons, fill forms, upload files
- Verify that pages display correctly and features work as expected

### Why Write Playwright Tests?

✅ **Catch integration bugs** that unit tests miss
✅ **Verify complete user workflows** (signup → payment → character creation)
✅ **Test JavaScript interactions** (TinyMCE editors, modals, AJAX)
✅ **Ensure cross-browser compatibility**
✅ **Document expected behavior** through executable examples

### When to Write Playwright Tests

**You MUST write Playwright tests when:**
- Adding a new feature with user-facing views
- Implementing complex multi-step workflows
- Adding forms with validation or dynamic behavior
- Creating features that involve file uploads/downloads
- Implementing payment flows or accounting features

---

## Test Structure

### Directory Organization

```
larpmanager/tests/
├── playwright/              # All E2E tests go here
│   ├── user_signup_simple_test.py
│   ├── orga_character_form_test.py
│   ├── exe_features_all_test.py
│   └── ...
├── unit/                    # Unit tests
│   └── ...
├── utils.py                 # Helper functions for tests
├── image.jpg                # Test image file
└── test_db.sql             # Test database dump
```

### Naming Conventions

**File naming:**
- `user_*.py` - Tests for user-facing features (public pages, signup, profile)
- `orga_*.py` - Tests for event organizer features (`/orga/` views)
- `exe_*.py` - Tests for organization-wide features (`/exe/` views)
- `*_test.py` - All test files end with `_test.py`

**Test function naming:**
- Start with `test_`
- Use descriptive names: `test_user_signup_simple`, `test_orga_character_form`

### Basic Test File Structure

```python
# Required imports
import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import go_to, login_orga, submit_confirm

# Mark this file as E2E test
pytestmark = pytest.mark.e2e


def test_feature_name(pw_page):
    """Test description explaining what this test does."""
    page, live_server, _ = pw_page

    # Setup: Login as organizer
    login_orga(page, live_server)

    # Test steps
    go_to(page, live_server, "/test/manage/features")
    page.get_by_role("button", name="Submit").click()

    # Assertions
    expect(page.locator("#banner")).to_contain_text("Success")
```

**Key elements:**
- `pytestmark = pytest.mark.e2e` - Marks file as E2E test (required)
- `pw_page` fixture - Provides browser page, server URL, and context
- Helper functions from `larpmanager.tests.utils`
- Playwright `expect` for assertions

---

## Writing Your First Test

### Step 1: Create Test File

Create a new file in `larpmanager/tests/playwright/`:

```bash
touch larpmanager/tests/playwright/user_profile_test.py
```

### Step 2: Write Basic Test

```python
import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import go_to, login_user, submit_confirm

pytestmark = pytest.mark.e2e


def test_user_can_update_profile(pw_page):
    """Test that a user can update their profile information."""
    page, live_server, _ = pw_page

    # Login as regular user
    login_user(page, live_server)

    # Navigate to profile page
    go_to(page, live_server, "/profile")

    # Fill in profile field
    page.locator("#id_phone").fill("+1234567890")

    # Submit form
    submit_confirm(page)

    # Verify success message
    expect(page.locator("#banner")).to_contain_text("Profile updated")
```

### Step 3: Understanding the pw_page Fixture

The `pw_page` fixture provides three values:

```python
def test_example(pw_page):
    page, live_server, context = pw_page
```

- **`page`** - Playwright Page object for browser interaction
- **`live_server`** - Base URL of test server (e.g., `http://127.0.0.1:8000`)
- **`context`** - Browser context (for advanced scenarios like multiple tabs)

**Configured in `conftest.py:65-89`:**
- Browser runs in headed mode if `--headed` flag passed or debugging in PyCharm
- Viewport: 1280x800
- Timeout: 60 seconds
- Auto-accepts dialogs (alerts/confirms)
- Raises error on HTTP 500 responses

---

## Helper Functions

LarpManager provides many helper functions in `larpmanager/tests/utils.py` to simplify test writing.

### Navigation

#### `go_to(page, live_server, path)`

Navigate to a path and wait for page to load.

```python
go_to(page, live_server, "/test/manage/features")
```

**What it does:**
- Constructs full URL: `{live_server}/{path}`
- Waits for load state: `load`, `domcontentloaded`, `networkidle`
- Checks for "Oops!" errors (auto-fails test if error page appears)

#### `go_to_check(page, full_url)`

Navigate to a full URL (not relative to live_server).

```python
go_to_check(page, "https://external-site.com/page")
```

### Authentication

#### `login_orga(page, live_server)`

Login as the organizer user (`orga@test.it` / `banana`).

```python
login_orga(page, live_server)
```

#### `login_user(page, live_server)`

Login as a regular user (`user@test.it` / `banana`).

```python
login_user(page, live_server)
```

#### `login(page, live_server, email)`

Login as a specific user (password is always `banana`).

```python
login(page, live_server, "custom@test.it")
```

#### `logout(page)`

Logout the current user.

```python
logout(page)
```

### Form Submission

#### `submit_confirm(page)`

Click the "Confirm" button and wait.

```python
page.locator("#id_name").fill("Test Name")
submit_confirm(page)
```

**What it does:**
- Scrolls button into view if needed
- Verifies button is visible
- Clicks the button

#### `submit(page)`

Click the "Submit" button and wait for network idle.

```python
page.locator("#id_email").fill("test@example.com")
submit(page)
```

### TinyMCE Rich Text Editor

#### `fill_tinymce(page, iframe_id, text, show=True, timeout=10000)`

Fill a TinyMCE editor with HTML content.

```python
fill_tinymce(page, "id_description", "<p>Test content</p>")
```

**Parameters:**
- `iframe_id` - The ID of the textarea (e.g., "id_description")
- `text` - HTML content to insert
- `show` - Whether to click "Show" link first (default: True)
- `timeout` - Wait timeout in milliseconds

**Example from `orga_character_form_test.py:236-239`:**
```python
def fill_presentation_text(page):
    fill_tinymce(page, "id_teaser", "baba")
    fill_tinymce(page, "id_text", "bebe")
```

### File Uploads

#### `load_image(page, element_id)`

Upload the test image to a file input.

```python
load_image(page, "#id_profile_picture")
```

Uses `larpmanager/tests/image.jpg` as the test file.

#### `upload(page, element_id, file_path)`

Upload a specific file to a file input.

```python
from pathlib import Path
csv_path = Path(__file__).parent / "test_data.csv"
upload(page, "#id_data_file", csv_path)
```

### Feature Activation

#### `check_feature(page, name)`

Enable a feature by checking its checkbox.

```python
check_feature(page, "Characters")
```

**Example from helper functions:**
```python
def check_feature(page, name):
    block = page.locator(".feature_checkbox").filter(has=page.get_by_text(name, exact=True))
    block.get_by_role("checkbox").check()
```

### Downloads

#### `check_download(page, link_text)`

Click a download link and verify the file downloads successfully.

```python
check_download(page, "Download CSV")
```

**What it does:**
- Clicks the link with specified text
- Waits for download (up to 100 seconds)
- Verifies file is not empty
- For ZIP files: extracts and validates CSV contents
- For CSV files: validates with pandas

### Utility Functions

#### `print_text(page)`

Print all visible text on the page (useful for debugging).

```python
print_text(page)
```

#### `handle_error(page, error, test_name)`

Take screenshot on error and re-raise.

```python
try:
    # test code
except Exception as e:
    handle_error(page, e, "test_user_signup")
```

---

## Recording Tests

LarpManager provides a script to **automatically generate test code** by recording your browser interactions.

### Using record-test.sh

**Step 1:** Run the recording script

```bash
./scripts/record-test.sh
```

**What it does:**
1. Checks you're not on `main` branch
2. Resets the test database (`python manage.py reset`)
3. Installs npm dependencies
4. Starts development server on port 8000
5. Opens Playwright code generator

**Step 2:** Interact with the application

- A browser window opens
- Perform the actions you want to test
- Playwright generates Python code as you click/type

**Step 3:** Copy generated code

The generated code appears in the Playwright Inspector window. Example:

```python
page.goto("http://127.0.0.1:8000/test/manage/features")
page.get_by_role("checkbox", name="Characters").check()
page.get_by_role("button", name="Confirm").click()
```

**Step 4:** Adapt code to LarpManager patterns

Replace generated code with helper functions:

```python
# Generated code:
page.goto("http://127.0.0.1:8000/test/manage/features")

# LarpManager pattern:
go_to(page, live_server, "/test/manage/features")

# Generated code:
page.get_by_role("button", name="Confirm").click()

# LarpManager pattern:
submit_confirm(page)
```

**Step 5:** Add to test file

```python
import pytest
from playwright.sync_api import expect
from larpmanager.tests.utils import go_to, login_orga, submit_confirm

pytestmark = pytest.mark.e2e


def test_enable_character_feature(pw_page):
    """Test enabling the character feature."""
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    go_to(page, live_server, "/test/manage/features")
    page.get_by_role("checkbox", name="Characters").check()
    submit_confirm(page)

    expect(page.locator("#banner")).to_contain_text("Features updated")
```

---

## Running Tests

### Run All Playwright Tests

```bash
./scripts/test_playwright.sh
```

**What it does:**
- Runs all tests in `larpmanager/tests/playwright/`
- Uses `$WORKERS` environment variable for parallel execution
- Reruns failed tests up to 5 times with 2-second delay

**Environment variable:**
```bash
export WORKERS=4  # Number of parallel workers
./scripts/test_playwright.sh
```

### Run Single Test File

```bash
pytest larpmanager/tests/playwright/user_signup_simple_test.py
```

### Run Specific Test Function

```bash
pytest larpmanager/tests/playwright/user_signup_simple_test.py::test_user_signup_simple
```

### Run in Headed Mode (See Browser)

```bash
pytest larpmanager/tests/playwright/user_signup_simple_test.py --headed
```

Useful for debugging - shows browser window during test execution.

### Run All Tests (Unit + Playwright)

```bash
pytest
```

This runs both unit tests and E2E tests.

---

## Best Practices

### 1. Break Tests Into Logical Functions

**Good:**
```python
def test_character_creation_workflow(pw_page):
    page, live_server, _ = pw_page

    setup_character_feature(page, live_server)
    create_character_form(page, live_server)
    fill_character_data(page)
    verify_character_created(page)


def setup_character_feature(page, live_server):
    login_orga(page, live_server)
    go_to(page, live_server, "/test/manage/features/character/on")


def create_character_form(page, live_server):
    go_to(page, live_server, "/test/manage/writing/form/")
    # ... form creation steps
```

**Bad:**
```python
def test_everything(pw_page):
    # 500 lines of sequential code
    page.goto(...)
    page.click(...)
    # ... no organization
```

**Why:** Breaking tests into functions makes them:
- Easier to read and understand
- Easier to debug when failures occur
- Reusable across multiple tests

**Example from `orga_character_form_test.py:31-80`:**
```python
def test_orga_character_form(pw_page):
    page, live_server, _ = pw_page
    login_orga(page, live_server)

    # Each step is a separate function
    add_field_text(page)
    add_field_available(page)
    add_field_multiple(page)
    add_field_restricted(page)
    add_field_special(page)
    create_first_char(live_server, page)
    check_first_char(page, live_server)
```

### 2. Use Descriptive Locators

**Good:**
```python
page.get_by_role("button", name="Submit")
page.get_by_label("Email address")
page.get_by_text("Registration confirmed")
```

**Better (when possible):**
```python
page.locator("#id_email")  # More stable than text-based
```

**Avoid:**
```python
page.locator("div > div > button")  # Fragile CSS selectors
```

### 3. Always Add Assertions

**Good:**
```python
submit_confirm(page)
expect(page.locator("#banner")).to_contain_text("Success")
```

**Bad:**
```python
submit_confirm(page)
# No verification - test passes even if submit failed
```

### 4. Use Helper Functions Consistently

**Good:**
```python
go_to(page, live_server, "/test/register")
submit_confirm(page)
```

**Bad:**
```python
page.goto(f"{live_server}/test/register")
page.wait_for_load_state("networkidle")
page.get_by_role("button", name="Confirm").click()
```

**Why:** Helper functions include error checking and waits that prevent flaky tests.

### 5. Test Complete Workflows

**Good:** Test the full user journey
```python
def test_signup_to_character_creation(pw_page):
    # 1. User signs up
    signup_user(page, live_server)

    # 2. User fills profile
    complete_profile(page)

    # 3. User creates character
    create_character(page)

    # 4. Organizer approves character
    logout(page)
    login_orga(page, live_server)
    approve_character(page)
```

**Bad:** Test isolated actions without context
```python
def test_click_button(pw_page):
    page.goto("http://example.com")
    page.click("button")
```

### 6. Clean Up Test Data

Tests should be **idempotent** - running them multiple times should produce the same result.

**Example from `user_signup_simple_test.py:57-62`:**
```python
# Delete previous signup before testing
go_to(page, live_server, "/test/manage/registrations")
page.locator("a:has(i.fas.fa-trash)").click()
```

### 7. Use Regular Expressions for Dynamic Text

**Good:**
```python
import re

page.get_by_role("link", name=re.compile(r"^Email notifications\s.+")).click()
```

**Why:** Handles dynamic content like "(3 unread)" or similar varying text.

**Example from `user_signup_simple_test.py:115`:**
```python
page.get_by_role("link", name=re.compile(r"^Email notifications\s.+")).click()
```

### 8. Wait for Elements When Needed

```python
# Wait for element to be visible
page.locator("#id_name").wait_for(state="visible")

# Wait for custom timeout
expect(page.locator("#banner")).to_be_visible(timeout=60000)
```

### 9. Test Both Success and Failure Cases

```python
def test_signup_validation(pw_page):
    page, live_server, _ = pw_page

    # Test missing required field
    go_to(page, live_server, "/test/register")
    submit_confirm(page)
    expect(page.locator("#banner")).to_contain_text("This field is required")

    # Test valid submission
    page.locator("#id_email").fill("valid@example.com")
    submit_confirm(page)
    expect(page.locator("#banner")).to_contain_text("Registration confirmed")
```

---

## Common Patterns

### Pattern 1: Feature Activation and Testing

```python
def test_new_feature(pw_page):
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    # Activate feature
    go_to(page, live_server, "/test/manage/features/my_feature/on")

    # Configure feature
    go_to(page, live_server, "/test/manage/config")
    page.get_by_role("link", name="My Feature").click()
    page.locator("#id_my_feature_enabled").check()
    submit_confirm(page)

    # Test feature works
    # ... test code
```

### Pattern 2: Form with Multiple Fields

```python
def test_character_form(pw_page):
    page, live_server, _ = pw_page

    login_orga(page, live_server)
    go_to(page, live_server, "/test/manage/characters/new")

    # Fill form fields
    page.locator("#id_name").fill("Aragorn")
    page.locator("#id_age").fill("87")
    page.locator("#id_race").select_option("human")
    page.get_by_role("checkbox", name="Is leader").check()

    # Fill TinyMCE
    fill_tinymce(page, "id_backstory", "<p>Ranger from the North</p>")

    # Upload image
    load_image(page, "#id_portrait")

    # Submit
    submit_confirm(page)

    # Verify
    expect(page.locator("#one")).to_contain_text("Character created")
```

### Pattern 3: Testing User and Organizer Views

```python
def test_character_visibility(pw_page):
    page, live_server, _ = pw_page

    # Organizer creates character
    login_orga(page, live_server)
    create_character(page, live_server, "Hero")
    logout(page)

    # User views character
    login_user(page, live_server)
    go_to(page, live_server, "/test/characters")
    expect(page.locator("#one")).to_contain_text("Hero")

    # User cannot edit
    expect(page.get_by_role("link", name="Edit")).not_to_be_visible()
```

### Pattern 4: File Download Verification

```python
def test_export_registrations(pw_page):
    page, live_server, _ = pw_page

    login_orga(page, live_server)
    go_to(page, live_server, "/test/manage/registrations")

    # Download CSV
    check_download(page, "Export CSV")

    # Download ZIP with multiple CSVs
    check_download(page, "Export All Data")
```

**From `utils.py:111-154`:** The `check_download` function automatically:
- Handles both CSV and ZIP downloads
- Validates CSV files with pandas
- Extracts and validates ZIP contents
- Retries up to 3 times on failure

### Pattern 5: Testing Mail Generation

```python
def test_signup_sends_email(pw_page):
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    # Enable email notifications
    go_to(page, live_server, "/test/manage/config")
    page.locator("#id_mail_signup_new").check()
    submit_confirm(page)

    # User signs up
    logout(page)
    go_to(page, live_server, "/test/register")
    page.get_by_role("button", name="Continue").click()
    submit_confirm(page)

    # Check mail was sent
    go_to(page, live_server, "/debug/mail")
    expect(page.locator("body")).to_contain_text("Registration confirmed")
```

**Example from `user_signup_simple_test.py:54-55`:**
```python
# test mails
go_to(page, live_server, "/debug/mail")
```

### Pattern 6: Visiting All Links (Smoke Test)

```python
def test_all_pages_load(pw_page):
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    # Visit every link on the site
    visited_links = set()
    links_to_visit = {live_server + "/manage/"}

    while links_to_visit:
        current_link = links_to_visit.pop()
        if current_link in visited_links:
            continue
        visited_links.add(current_link)

        go_to_check(page, current_link)

        # Add new links found on page
        add_links_to_visit(links_to_visit, page, visited_links)
```

**From `exe_features_all_test.py:41-53`** - This pattern ensures all pages are accessible without errors.

### Pattern 7: Testing Available/Max Fields

```python
def test_limited_availability(pw_page):
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    # Create trait with max 1 available
    go_to(page, live_server, "/test/manage/traits/new")
    page.locator("#id_name").fill("Rare Trait")
    page.locator("#id_max_available").fill("1")
    submit_confirm(page)

    # First character takes it
    create_character_with_trait(page, "Character 1", "Rare Trait")
    expect(page.locator("#one")).to_contain_text("Rare Trait")

    # Second character sees it disabled
    create_character_with_trait(page, "Character 2", "Rare Trait")
    expect(page.get_by_role("checkbox", name="Rare Trait")).to_be_disabled()
```

**Example from `orga_character_form_test.py:94-107`:**
```python
expect(page.locator("#id_q6")).to_match_aria_snapshot(
    '- combobox:\n  - option "-------" [disabled] [selected]\n  - option "all"\n  - option "few - (Available 1)"'
)
```

---

## Troubleshooting

### Test Fails with "Element not found"

**Cause:** Element hasn't loaded yet or selector is wrong

**Solutions:**

1. Add explicit wait:
```python
page.locator("#my-element").wait_for(state="visible")
```

2. Increase timeout:
```python
expect(page.locator("#my-element")).to_be_visible(timeout=30000)
```

3. Check selector in browser DevTools:
```python
# Run test in headed mode to inspect
pytest path/to/test.py --headed
```

### Test Passes Locally but Fails in CI

**Cause:** Timing issues or race conditions

**Solutions:**

1. Use `go_to()` instead of direct `page.goto()`:
```python
# Bad - no waits
page.goto(f"{live_server}/test/page")

# Good - includes waits
go_to(page, live_server, "/test/page")
```

2. Use `submit_confirm()` instead of direct clicks:
```python
# Bad
page.get_by_role("button", name="Confirm").click()

# Good - includes scroll and visibility checks
submit_confirm(page)
```

3. Add network idle wait:
```python
page.wait_for_load_state("networkidle")
```

### TinyMCE Editor Not Filling

**Cause:** Editor not initialized or hidden

**Solutions:**

1. Ensure editor is visible:
```python
fill_tinymce(page, "id_description", "content", show=True)
```

2. Increase timeout:
```python
fill_tinymce(page, "id_description", "content", timeout=30000)
```

3. Check the iframe_id matches the textarea ID:
```python
# HTML: <textarea id="id_backstory">
fill_tinymce(page, "id_backstory", "text")  # Correct
```

### File Upload Fails

**Cause:** File path is wrong or element not visible

**Solutions:**

1. Ensure element is visible:
```python
page.locator("#id_file").scroll_into_view_if_needed()
load_image(page, "#id_file")
```

2. Use correct path:
```python
from pathlib import Path
image_path = Path(__file__).parent / "test_file.jpg"
upload(page, "#id_file", image_path)
```

### Download Test Fails

**Cause:** Download times out or file is invalid

**Solutions:**

1. The `check_download` function already retries 3 times
2. Ensure link text is exact:
```python
check_download(page, "Download CSV")  # Must match link text exactly
```

3. For large files, download manually:
```python
with page.expect_download(timeout=120000) as download_info:
    page.click("text=Large Export")
download = download_info.value
assert download.path() is not None
```

### Test Database Not Clean

**Cause:** Previous test left data

**Solution:** Database is automatically truncated between tests by `conftest.py:178-190`.

If issues persist:
```bash
python manage.py reset
pytest larpmanager/tests/playwright/your_test.py
```

### Test Hangs Indefinitely

**Cause:** Waiting for element that never appears

**Solutions:**

1. Run in headed mode to see what's happening:
```bash
pytest path/to/test.py --headed
```

2. Add timeout to specific waits:
```python
page.locator("#element").wait_for(state="visible", timeout=10000)
```

3. Check for JavaScript errors in console (add to test):
```python
page.on("console", lambda msg: print(f"Console: {msg.text}"))
```

---

## Related Documentation

- **[Features and Permissions Guide](01-features-and-permissions.md)** - Understanding features you'll test
- **[Roles and Context Guide](02-roles-and-context.md)** - View structure and permissions
- **[Configuration System Guide](03-configuration-system.md)** - Testing configuration options
- **[Contributing Guide](../README.md#contributing)** - Overall workflow
- **[CLAUDE.md Testing Section](../CLAUDE.md#testing-strategy)** - Testing overview

**External Resources:**
- [Playwright Documentation](https://playwright.dev/python/)
- [Playwright Locators Guide](https://playwright.dev/python/docs/locators)
- [Playwright Assertions](https://playwright.dev/python/docs/test-assertions)

---

## Summary

When adding new features to LarpManager:

1. **Write Playwright tests** covering the complete user workflow
2. **Use `./scripts/record-test.sh`** to generate test code quickly
3. **Break tests into logical functions** for readability
4. **Use helper functions** from `larpmanager/tests/utils.py`
5. **Test both success and failure cases**
6. **Run tests before committing:**
   ```bash
   pytest larpmanager/tests/playwright/your_test.py
   ```
7. **Verify all tests pass:**
   ```bash
   pytest  # Run all tests
   ```

**Remember:** From README.md contributing guidelines:
> If you're creating a new feature, write a playwright test suite that covers it.

Good tests ensure your feature works correctly and continues working as the codebase evolves.

**Next steps:** Read the [Features and Permissions Guide](01-features-and-permissions.md) to understand how to structure the features you'll be testing.
