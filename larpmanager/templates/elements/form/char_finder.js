{% load tz show_tags static  i18n %}

<script>

window.addEventListener('DOMContentLoaded', function() {
    $(function() {

        // char finder
        $(document).on('keydown', function(e) {
            if (e.ctrlKey && e.altKey && e.key.toLowerCase() === 'h') {
                e.preventDefault();
                char_finder(false);
            }
        });

        function setUpCharFinder(key) {
            const editor = tinymce.get(key);
            if (!editor) return;
            editor.on('keydown', function(ev) {
                if (ev.ctrlKey && ev.altKey && ev.key.toLowerCase() === 'h') {
                    ev.preventDefault();
                    char_finder(key);
                }
            });
        }

        {% for question in form.questions %}
            {% if question.typ == 'e' %}
                setUpCharFinder('id_q{{ question.id }}');
            {% elif question.typ == 'text' %}
                setUpCharFinder('id_text');
            {% elif question.typ == 'teaser' %}
                setUpCharFinder('id_teaser');
            {% endif %}
        {% endfor %}

        function close_char_finder() {
            $('#char-finder-popup').fadeOut(200);
        }
        $('#char-finder-close').on('click', close_char_finder);

        var savedFocusElem = null;
        var savedCursorPos = null;
        var bookmark = null;
        var key = null;

        function char_finder(tinymce_key) {

            savedFocusElem = null;
            savedCursorPos = null;
            bookmark = null;
            key = null;

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

            $('#char-finder-popup').fadeIn(200);
        }

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
                insertReference(' #' + result.number);
            });
        });

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
    });
});

</script>
