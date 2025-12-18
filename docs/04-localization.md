# Developer Guide: Localization and Translation

This guide explains how to write translatable text, manage translations, and customize text for specific organizations.

**Key principle:** Always write interface text in **simple, direct English**. The translation system will handle converting it to other languages.

## Table of Contents

1. [Overview](#overview)
2. [Writing Translatable Code](#writing-translatable-code)
3. [Translation Workflow](#translation-workflow)
4. [Django Translation System](#django-translation-system)
5. [AssociationText](#associationtext)
6. [AssociationTranslation](#associationtranslation)
7. [Best Practices](#best-practices)
8. [Examples](#examples)

---

## Overview

LarpManager supports multiple languages through Django's internationalization (i18n) system, enhanced with:

- **Automatic translation** via DeepL API
- **Per-organization text customization** via AssociationText
- **Per-organization translation overrides** via AssociationTranslation

### Supported Languages

The system currently supports:
- **en** - English (source language)
- **it** - Italian
- **es** - Spanish
- **fr** - French
- **de** - German
- **nl** - Dutch
- **cs** - Czech
- **nb** - Norwegian Bokmål
- **pl** - Polish
- **sv** - Swedish

---

## Writing Translatable Code

### Golden Rules

1. **Always write in simple, direct English**
2. **Use short, clear sentences**
3. **Avoid idioms, slang, or complex expressions**
4. **Be consistent with terminology**

### In Python Code

Use Django's translation functions:

```python
from django.utils.translation import gettext_lazy as _

# Simple string
page_title = _("Configuration")

# String with context (for disambiguation)
from django.utils.translation import pgettext_lazy

genre_label = pgettext_lazy("event", "Genre")
music_genre = pgettext_lazy("music", "Genre")
```

**Why `gettext_lazy`?**
- Use `gettext_lazy` (aliased as `_`) in model fields, form fields, and class-level attributes
- The translation happens when the string is actually rendered, not when the code is loaded
- This ensures the correct language is used based on the current request

### In Templates

Use Django's translation template tags:

```html
{% load i18n %}

{# Simple translation #}
<h1>{% trans "Welcome" %}</h1>

{# Translation with variable #}
<p>{% blocktrans %}Hello {{ username }}!{% endblocktrans %}</p>

{# Translation with context #}
<label>{% pgettext "form label" "Name" %}</label>

{# Pluralization #}
{% blocktrans count counter=items|length %}
    There is {{ counter }} item.
{% plural %}
    There are {{ counter }} items.
{% endblocktrans %}
```

### In JavaScript

For JavaScript, strings are translated server-side and passed to the template:

```python
# In view
context["js_strings"] = {
    "confirm_delete": _("Are you sure you want to delete this item?"),
    "success": _("Operation completed successfully"),
}
```

```html
<script>
    const strings = {{ js_strings|safe }};
    if (confirm(strings.confirm_delete)) {
        // ...
    }
</script>
```

### What to Mark for Translation

✅ **Do translate:**
- User-facing text
- Form labels and help text
- Error messages
- Button labels
- Page titles and descriptions
- Email subject lines and bodies

❌ **Don't translate:**
- Code identifiers (variable names, function names)
- URL slugs
- Configuration keys
- Log messages (internal debugging)
- Database field names

---

## Translation Workflow

The translation process is handled by the `./scripts/translate.sh` script, which automates the entire workflow.

### The Complete Process

```bash
./scripts/translate.sh
```

This script performs the following steps:

#### 1. **Prepare Translations** (`scripts/prepare_trans.py`)

Extracts translatable strings from fixtures (features, permissions, modules) and creates a template file:

```python
# Reads from:
# - larpmanager/fixtures/module.yaml
# - larpmanager/fixtures/feature.yaml
# - larpmanager/fixtures/association_permission.yaml
# - larpmanager/fixtures/event_permission.yaml
# - larpmanager/fixtures/permission_module.yaml

# Creates:
# - larpmanager/templates/trans.html (temporary translation template)
```

#### 2. **Extract Messages** (`django-admin makemessages`)

Scans Python and template files for translatable strings and updates `.po` files:

```bash
cd larpmanager
django-admin makemessages --all --no-location
```

This creates/updates files in `larpmanager/locale/[lang]/LC_MESSAGES/django.po`

**What happens:**
- Scans all Python files for `_()`, `gettext()`, `pgettext()` calls
- Scans all templates for `{% trans %}`, `{% blocktrans %}` tags
- Updates each language's `.po` file with new/changed strings
- Marks strings as "fuzzy" if they've been modified

#### 3. **Auto-Translate** (`python manage.py translate`)

Uses DeepL API to automatically translate untranslated and fuzzy strings:

```python
# For each language (except English):
# 1. Reads larpmanager/locale/[lang]/LC_MESSAGES/django.po
# 2. Finds entries without translation or marked as fuzzy
# 3. Translates them using DeepL API
# 4. Updates the .po file with translations
# 5. Saves the file
```

**DeepL API Integration:**
- Requires `DEEPL_API_KEY` in `main/settings/dev.py`
- Free tier: 500,000 characters/month
- Get API key at: https://www.deepl.com/en/pro

#### 4. **Review Translations**

After auto-translation, the script pauses for review:

```
Translations have been generated. Please review them before continuing.
Press Enter to continue...
```

**What to review:**
- Technical terms may need correction
- Context-specific translations
- Pluralization rules
- Formal vs. informal tone (varies by language)

**Common issues to check:**
- Brand names should not be translated
- UI elements should match design conventions
- Gender agreement in Romance languages
- Capitalization rules differ by language

#### 5. **Validate Format** (`msgfmt --check-format`)

Validates that all `.po` files are correctly formatted:

```bash
find . -name "*.po" | while read -r file; do
  msgfmt --check-format "$file" -o /dev/null
done
```

If validation fails, the script exits with an error and you must fix the `.po` file manually.

#### 6. **Compile Messages** (`django-admin compilemessages`)

Compiles `.po` files into binary `.mo` files that Django uses at runtime:

```bash
cd larpmanager
django-admin compilemessages
```

Creates `django.mo` files alongside each `django.po` file.

### Manual Translation

If you need to manually edit translations:

1. Open the appropriate `.po` file:
   ```bash
   nano larpmanager/locale/it/LC_MESSAGES/django.po
   ```

2. Find the string to translate:
   ```po
   msgid "Configuration"
   msgstr "Configurazione"
   ```

3. Edit the `msgstr` value

4. Compile messages:
   ```bash
   cd larpmanager
   django-admin compilemessages
   ```

5. Restart the development server to see changes

### When to Run Translations

Run `./scripts/translate.sh` when:

✅ You've added new translatable strings to code
✅ You've modified existing strings
✅ You've added new features/permissions (they're in fixtures)
✅ Before committing changes (pre-commit hook does this automatically)

---

## Django Translation System

### How It Works

1. **Source Language:** All code uses English strings
2. **Extraction:** `makemessages` finds translatable strings
3. **Storage:** Strings stored in `.po` (Portable Object) files
4. **Translation:** DeepL or manual translation fills in `msgstr` values
5. **Compilation:** `compilemessages` creates binary `.mo` files
6. **Runtime:** Django loads the appropriate `.mo` file based on user's language

### PO File Format

Example from `larpmanager/locale/it/LC_MESSAGES/django.po`:

```po
#: larpmanager/forms/association.py:42
msgid "Configuration"
msgstr "Configurazione"

#: larpmanager/forms/association.py:43
msgid "Manage configuration of activated features"
msgstr "Gestisci la configurazione delle funzionalità attivate"

# Context-based translation
msgctxt "event"
msgid "Genre"
msgstr "Genere"

msgctxt "music"
msgid "Genre"
msgstr "Genere musicale"

# Pluralization
msgid "There is %(count)d item."
msgid_plural "There are %(count)d items."
msgstr[0] "C'è %(count)d elemento."
msgstr[1] "Ci sono %(count)d elementi."
```

**Key elements:**
- `#:` - Source file location (removed by translate.sh to reduce clutter)
- `msgid` - Original English text
- `msgstr` - Translated text
- `msgctxt` - Context for disambiguation
- `msgid_plural` - Plural form (English)
- `msgstr[n]` - Plural forms (varies by language)

### Language Detection

Django determines the user's language based on:

1. **URL parameter:** `?lang=it`
2. **User preference:** Stored in session
3. **Browser language:** Accept-Language header
4. **Default:** Set in `settings.LANGUAGE_CODE` (usually `en`)

---

## AssociationText

AssociationText allows organizations to customize **long, complex texts** like legal notices, terms of service, and email templates.

### When to Use AssociationText

✅ **Use for:**
- Legal notices and privacy policies
- Terms and conditions
- Long email templates
- Footer content
- Organization-specific instructions
- Membership information

❌ **Don't use for:**
- Short UI labels (use translations instead)
- Button text (use translations)
- Single words or phrases (use AssociationTranslation)

### Available Text Types

Defined in `AssociationTextType` enum in `larpmanager/models/association.py`:

**Core types (always available):**
- `PROFILE` - Content added at the top of user profile page
- `HOME` - Content added at the top of main calendar page
- `SIGNUP` - Text added at bottom of signup confirmation emails
- `MEMBERSHIP` - Membership request form content filled with user data
- `STATUTE` - Statute information shown on membership page
- `LEGAL` - Legal notice page content
- `FOOTER` - Content added to bottom of all pages
- `TOC` - Terms and conditions shown in registration form
- `RECEIPT` - Receipt content for payments
- `SIGNATURE` - Signature added to all emails sent
- `PRIVACY` - Privacy policy page content

**Reminder types (require "remind" feature):**
- `REMINDER_MEMBERSHIP` - Email reminding participants to fill membership request
- `REMINDER_MEMBERSHIP_FEE` - Email reminding participants to pay membership fee
- `REMINDER_PAY` - Email reminding participants to pay signup fee

### Adding New Text Types

**Important:** Adding new text types requires code modification.

**Step 1:** Add to `AssociationTextType` enum

```python
# In larpmanager/models/association.py

class AssociationTextType(models.TextChoices):
    # ... existing types ...
    WELCOME = "w", _("Welcome Email")  # New type
```

**Step 2:** Use in code

```python
# In a view or email function
from larpmanager.cache.association_text import get_association_text
from larpmanager.models.association import AssociationTextType

def send_welcome_email(association_id, member_email, language="en"):
    """Send welcome email using cached association text."""
    email_body = get_association_text(
        association_id,
        AssociationTextType.WELCOME,
        language
    )
    # Use email_body to send email
```

### Managing AssociationTexts

Organizations manage their texts through:

**View:** `Organization -> Texts` (requires `exe_texts` permission)

**Features:**
- Create text in multiple languages
- Mark default text per type
- Rich text editor (TinyMCE) for formatting
- Preview before saving

---

## AssociationTranslation

AssociationTranslation allows organizations to **override specific translations** without modifying global `.po` files.

### When to Use AssociationTranslation

✅ **Use for:**
- Organization-specific terminology (e.g., "Character" → "Hero")
- Regional variations within same language
- Brand-specific vocabulary
- Customizing specific UI terms

❌ **Don't use for:**
- Long text blocks (use AssociationText)
- Entire pages (use AssociationText)
- Technical terms that shouldn't change

### Model Structure

**Key fields:**
- `msgid` - The original English text from code
- `msgstr` - The organization's custom translation
- `context` - Optional context for disambiguation (like `msgctxt`)
- `language` - Target language for this translation
- `active` - Enable/disable without deletion

### How It Works

1. **Code contains:** `_("Character")`
2. **Global translation (Italian):** "Personaggio"
3. **Organization override:** Create AssociationTranslation with:
   - `msgid` = "Character"
   - `msgstr` = "Eroe"
   - `language` = "it"
4. **Result:** For that organization, "Character" displays as "Eroe" instead of "Personaggio"

### Adding Translation Overrides

**No code modification required!** Organizations can add overrides through the admin interface.

**Step 1:** Go to `Organization -> Translations` (requires `exe_translations` permission and `Translations` feature)

**Step 2:** Click "Add translation override"

**Step 3:** Fill in the form:
- **msgid:** The English text you want to override (copy from the interface)
- **msgstr:** Your custom translation
- **Language:** Select target language
- **Context:** (Optional) If the same word appears in different contexts
- **Active:** Check to enable

**Example:**

```
msgid: Character
msgstr: Hero
Language: English (en)
Context: (empty)
Active: ✓
```

Now, for this organization, everywhere "Character" appears, it will show "Hero" instead.

### With Context

If you want to override only specific occurrences:

```python
# In code, different contexts:
character_label = pgettext("player", "Character")
story_character = pgettext("story", "Character")
```

**Override only player context:**
```
msgid: Character
msgstr: Hero
Context: player
Language: English (en)
```

Result:
- Player context: "Hero"
- Story context: "Character" (unchanged)

### Middleware Integration

AssociationTranslation works through `AssociationTranslationMiddleware`:

1. Intercepts translation requests
2. Checks if organization has custom translation for this msgid/context/language
3. If found and active, returns custom translation
4. Otherwise, returns standard translation from `.po` files

---

## Best Practices

### Writing Translatable Text

✅ **Do:**

```python
# Good - simple, direct
_("Save")
_("Delete this item")
_("Email address is required")

# Good - with context
pgettext("button", "Close")
pgettext("verb", "Close")

# Good - with variables
_("Welcome, %(name)s!") % {"name": username}
```

❌ **Don't:**

```python
# Bad - slang/idioms
_("Piece of cake!")  # Hard to translate

# Bad - complex sentence
_("In order to proceed with the configuration, you should...")  # Too wordy

# Bad - concatenation
_("Hello") + " " + username  # Breaks translations

# Bad - mixed content
_("Click <a href='...'>here</a>")  # HTML in translation
```

### Translation Review

When reviewing auto-translated text:

1. **Check terminology consistency**
   - "Character" should always translate the same way
   - Technical terms should be correct

2. **Verify context**
   - "Run" (noun) vs "Run" (verb) need different translations
   - "Save" (verb) vs "Safe" (adjective)

3. **Test pluralization**
   - Different languages have different plural rules
   - Some languages have 3+ plural forms

4. **Check gender agreement**
   - Romance languages need gender-correct adjectives
   - Some nouns have different translations based on gender

5. **Verify formality**
   - Some languages have formal/informal pronouns
   - Match the project's tone consistently

### Using AssociationText vs AssociationTranslation

**Use AssociationText when:**
- Text is paragraph-length or longer
- Content is organization-specific (not a translation)
- Needs rich text formatting
- Examples: legal notices, email templates

**Use AssociationTranslation when:**
- Overriding specific UI terms
- Single words or short phrases
- Want different terminology than default translation
- Examples: "Character" → "Hero", "Event" → "Game"

**Use regular translations when:**
- Standard UI text
- Applies to all organizations
- No customization needed

---

## Examples

### Example 1: Adding Translatable Feature

**Step 1:** Write code with translation markers

```python
# In larpmanager/forms/event.py

class OrgaCharacterForm(forms.ModelForm):
    class Meta:
        model = Character
        fields = ['name', 'description']
        labels = {
            'name': _('Character name'),
            'description': _('Character description'),
        }
        help_texts = {
            'name': _('Enter the name of your character'),
            'description': _('Provide a detailed background for your character'),
        }
```

**Step 2:** Run translation script

```bash
./scripts/translate.sh
```

**Step 3:** Review auto-generated translations

```po
# larpmanager/locale/it/LC_MESSAGES/django.po

msgid "Character name"
msgstr "Nome del personaggio"

msgid "Enter the name of your character"
msgstr "Inserisci il nome del tuo personaggio"
```

**Step 4:** Commit changes

```bash
git add larpmanager/locale/
git commit -m "Add character form translations"
```

### Example 2: Context-Based Translation

When the same word has different meanings:

```python
# In view
from django.utils.translation import pgettext_lazy

class EventForm(forms.ModelForm):
    # "Close" as in "close the form"
    close_button = pgettext_lazy("button", "Close")

    # "Close" as in "nearby"
    proximity_label = pgettext_lazy("distance", "Close")
```

In Italian:
- Button context: "Chiudi" (to close)
- Distance context: "Vicino" (near)

### Example 3: Using AssociationText

**Requirement:** Organization wants custom privacy policy

**Step 1:** Organization goes to `/exe/texts/`

**Step 2:** Clicks "Add text"

**Step 3:** Fills form:
- Type: Privacy Policy
- Language: English
- Default: Yes
- Content: [Custom privacy policy text with rich formatting]

**Step 4:** Code retrieves the text:

```python
from larpmanager.cache.association_text import get_association_text
from larpmanager.models.association import AssociationTextType
from larpmanager.utils.core.base import get_context


def privacy_policy(request):
    context = get_context(request)

    # Try to get organization's custom text, otherwise use default
    context["privacy_content"] = (
            get_association_text(
                context["association_id"],
                AssociationTextType.PRIVACY,
                request.LANGUAGE_CODE
            ) or _("Default privacy policy text")
    )

    return render(request, "privacy.html", context)
```

### Example 4: Using AssociationTranslation

**Requirement:** Fantasy LARP organization wants "Character" to say "Hero" everywhere

**Step 1:** Go to `/exe/translations/`

**Step 2:** Add translation override:

```
msgid: Character
msgstr: Hero
Language: en
Context: (empty)
Active: ✓
```

**Result:**
- All buttons showing "Character" now show "Hero"
- All labels showing "Character" now show "Hero"
- Form fields, menus, etc. - all updated
- Other organizations still see "Character"

**With Italian:**

```
msgid: Character
msgstr: Eroe
Language: it
Context: (empty)
Active: ✓
```

Now Italian users of this organization see "Eroe" instead of "Personaggio".

### Example 5: Pluralization

**Code:**

```python
# In template
{% load i18n %}

{% blocktrans count counter=characters|length %}
    You have {{ counter }} character.
{% plural %}
    You have {{ counter }} characters.
{% endblocktrans %}
```

**After translation (Italian):**

```po
msgid "You have %(counter)s character."
msgid_plural "You have %(counter)s characters."
msgstr[0] "Hai %(counter)s personaggio."
msgstr[1] "Hai %(counter)s personaggi."
```

**Result:**
- 1 character: "Hai 1 personaggio"
- 2+ characters: "Hai 5 personaggi"

---

## Summary

LarpManager's localization system provides three levels of customization:

1. **Global translations** (Django `.po` files)
   - For standard UI text
   - Auto-translated with DeepL
   - Maintained by developers

2. **AssociationText** (long custom text)
   - For organization-specific content
   - Rich text with formatting
   - Requires code changes to add new types
   - Managed by organization admins

3. **AssociationTranslation** (terminology overrides)
   - For customizing specific terms
   - Single words or short phrases
   - No code changes needed
   - Managed by organization admins

**Key principles:**
- Write all code in simple, direct English
- Run `./scripts/translate.sh` before committing
- Review auto-generated translations for accuracy
- Use AssociationText for long content
- Use AssociationTranslation for terminology customization

**Related guides:**
- [Features and Permissions Guide](01-features-and-permissions.md) - Adding translatable features
- [Configuration System Guide](03-configuration-system.md) - Feature-specific settings
- [Playwright Testing Guide](05-playwright-testing.md) - Testing translated interfaces

By following these guidelines, you ensure LarpManager remains accessible to users worldwide while allowing organizations to customize their experience.
