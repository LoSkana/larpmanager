{% load tz show_tags static  i18n %}

<script>

window.addEventListener('DOMContentLoaded', function() {
    $(function() {

        // char finder
        $(document).on('keydown', function(e) {
            if (e.ctrlKey && e.altKey && e.key.toLowerCase() === 'h') {
                e.preventDefault();
                char_finder();
            }
        });

        if (window.tinymce) {
            tinymce.on('AddEditor', function(e) {
                e.editor.on('keydown', function(ev) {
                    if (ev.ctrlKey && ev.altKey && ev.key.toLowerCase() === 'h') {
                        ev.preventDefault();
                        console.log('ciao');
                        char_finder();
                    }
                });
            });
        }

        function close_char_finder() {
            $('#char-finder-popup').fadeOut(200);
        }
        $('#char-finder-close').on('click', close_char_finder);

        var savedFocusElem = null;
        var savedCursorPos = null;

        function char_finder() {

            var $active = $(document.activeElement);
            if ($active.is('input, textarea')) {
                savedFocusElem = $active;
                var el = $active.get(0);
                savedCursorPos = {
                    start: el.selectionStart,
                    end: el.selectionEnd
                };
            } else {
                savedFocusElem = null;
                savedCursorPos = null;
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
                insertReference('#' + result.number);
            });
        });

        function insertReference(text) {

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
