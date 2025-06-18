{% load tz show_tags static  i18n %}

<script>

function setUpCharFinder(key) {
    const editor = tinymce.get(key);
    if (!editor) return;
    editor.on('keydown', function(ev) {
        const triggerKeys = ['#', '@', '^'];
        if (triggerKeys.includes(ev.key)) {
            ev.preventDefault();
            char_finder(ev.key, key);
        }
    });
}

function close_char_finder() {
    $('#char-finder-popup').fadeOut(200);

    const x = window.scrollX;
    const y = window.scrollY;

    if (key) {
        editor = tinymce.get(key);
        editor.focus();
        editor.selection.moveToBookmark(bookmark);
    }

    if (savedFocusElem && savedCursorPos) {
        savedFocusElem.focus();
    }

    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            window.scrollTo(x, y);
        });
    });
}

var savedFocusElem = null;
var savedCursorPos = null;
var bookmark = null;
var key = null;
var symbol_key = null;

function char_finder(ev_key, tinymce_key) {

    savedFocusElem = null;
    savedCursorPos = null;
    bookmark = null;
    key = null;
    symbol_key = ev_key;

    if (tinymce_key) {
        key = tinymce_key;
        editor = tinymce.get(key);
        bookmark = editor.selection.getBookmark(2, true);
    } else {
        var $active = $(document.activeElement);
        if ($active.is('input, textarea')) {
            savedFocusElem = $active;
            var el = $active.get(0);
            savedCursorPos = {
                start: el.selectionStart,
                end: el.selectionEnd
            };
        }
    }

    char_finder_symbol = null;
    if (ev_key === '#')
        char_finder_symbol = '#XX: ' + '{% trans "bidirectional relationships" %}';
    else if (ev_key === '@')
        char_finder_symbol = '@XX: ' + '{% trans "unidirectional relationships" %}';
    else if (ev_key === '^')
        char_finder_symbol = '^XX: ' + '{% trans "simple reference" %}';

    $('.char-finder-symbol').text(char_finder_symbol);

    $('#char-finder-popup').fadeIn(200);

    $('#char_finder').select2('open');
}

function insertReference(text) {
    if (key) {
        editor = tinymce.get(key);
        editor.selection.moveToBookmark(bookmark);
        editor.insertContent(text);
    }

    if (savedFocusElem && savedCursorPos) {
        var el = savedFocusElem.get(0);
        var val = savedFocusElem.val();
        var before = val.substring(0, savedCursorPos.start);
        var after = val.substring(savedCursorPos.end);
        savedFocusElem.val(before + text + after);

        var newPos = savedCursorPos.start + text.length;
        el.selectionStart = el.selectionEnd = newPos;
        savedFocusElem.focus();
    }
}

window.addEventListener('DOMContentLoaded', function() {
    $(function() {

        // char finder
        $(document).on('keydown', function(ev) {
            const triggerKeys = ['#', '@', '^'];
            if (triggerKeys.includes(ev.key)) {
                ev.preventDefault();
                char_finder(ev.key, false);
            }
        });

        $('#char-finder-close').on('click', close_char_finder);

        {% for question in form.questions %}
            {% if question.typ == 'e' %}
                setUpCharFinder('id_q{{ question.id }}');
            {% elif question.typ == 'text' %}
                setUpCharFinder('id_text');
            {% elif question.typ == 'teaser' %}
                setUpCharFinder('id_teaser');
            {% endif %}
        {% endfor %}

        $('#char_finder').on('change', function(e) {
            var value = $(this).val();
            if (value == null || value == '') return;

            request = $.ajax({
                url: "{% url 'orga_character_get_number' event.slug run.number %}",
                data: { idx: value },
                method: "POST",
                datatype: "json",
            });

            request.done(function(result) {

                $('#char_finder').val(null).trigger('change');
                close_char_finder();
                insertReference(symbol_key + result.number);
            });
        });
    });
});

</script>
