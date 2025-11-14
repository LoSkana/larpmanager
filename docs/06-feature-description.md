# Prologue Feature Documentation

## Overview
The Prologue feature enables organizers to create short introductory paragraphs for each act of an event, which are delivered to participants through their character sheets to guide them into the story.

## Feature Configuration
- **Feature Slug**: `prologue`
- **Scope**: Event-specific (`overall=false`)
- **Module**: `writing`

## Permissions
Two permissions control access to prologue functionality:

### orga_prologue_types
Grants access to manage prologue types (categories). Organizers can create and edit prologue type definitions that serve as templates for organizing prologues by act or narrative structure.

### orga_prologues
Grants access to create, edit, and view individual prologues. Organizers can assign prologues to specific characters and link them to prologue types.

## Data Model Architecture

### PrologueType Model
```python
class PrologueType(Writing):
    # Inherits: number, name, event, text fields from Writing base class
```
Acts as a category or template defining the type of prologue (e.g., "Act 1", "Act 2", "Epilogue").

### Prologue Model
```python
class Prologue(Writing):
    typ = models.ForeignKey(PrologueType, on_delete=models.CASCADE, related_name="prologues")
    characters = models.ManyToManyField(Character, related_name="prologues_list", blank=True)
```
Contains the actual prologue content assigned to one or more characters, categorized by type.

## Management Views

### Prologue Type Management
```python
def orga_prologue_types(request, event_slug):
    context = check_event_context(request, event_slug, "orga_prologue_types")
    return writing_list(request, context, PrologueType, "prologue_type")

def orga_prologue_types_edit(request, event_slug, num):
    context = check_event_context(request, event_slug, "orga_prologue_types")
    if num != 0:
        get_prologue_type(context, num)
    return writing_edit(request, context, PrologueTypeForm, "prologue_type", None)
```
Organizers must first create at least one prologue type before creating prologues.

### Prologue Content Management
```python
def orga_prologues_edit(request, event_slug, num):
    context = check_event_context(request, event_slug, "orga_prologues")
    if not context["event"].get_elements(PrologueType).exists():
        messages.warning(request, _("You must create at least one prologue type..."))
        return redirect("orga_prologue_types_edit", event_slug=event_slug, num=0)
    if num != 0:
        get_prologue(context, num)
    return writing_edit(request, context, PrologueForm, "prologue", TextVersionChoices.PROLOGUE)
```
Validates that prologue types exist before allowing prologue creation. Supports versioning through `TextVersionChoices.PROLOGUE`.

## Character Sheet Integration

### Loading Prologues
```python
def get_character_sheet_prologue(context: dict):
    if "prologue" not in context["features"]:
        return
    context["sheet_prologues"] = []
    for prologue in context["character"].prologues_list.order_by("typ__number"):
        prologue.data = prologue.show_complete()
        context["sheet_prologues"].append(prologue)
```
Prologues are automatically included in character sheets when the feature is enabled, ordered by prologue type number to ensure proper act sequence.

### Participant Display
```html
{% for p in sheet_prologues %}
    <h2 class="c">{{ p.data.name }} ({{ p.typ.name }})</h2>
    <div class="plot">{% show_char p.data run 1 %}</div>
{% endfor %}
```
Each prologue displays its name, type, and full content. The template includes a warning message asking participants not to read prologues before their referenced act.

## Workflow
1. **Setup**: Organizers enable the prologue feature for an event
2. **Type Creation**: Create prologue types (e.g., "Act 1", "Act 2", "Final Act")
3. **Content Creation**: Write prologues and assign them to prologue types
4. **Character Assignment**: Link prologues to specific characters via many-to-many relationship
5. **Delivery**: Prologues automatically appear in character sheets, ordered by type number
6. **Participant Access**: Players view prologues as guided introductions for each story act
