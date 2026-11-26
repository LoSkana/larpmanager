{% load tz show_tags static i18n %}

<script nonce="{{ csp_nonce }}">

var tinymce_count = ["teaser", "text", "e"];

// Show the character preview below the point (x, y), in viewport coordinates.
function openCharTip(x, y, html) {
    const content = document.createElement('div');
    content.className = 'lm-tip-content show_char';
    content.innerHTML = html;
    const point = {getBoundingClientRect: () => new DOMRect(x, y, 0, 0)};
    lmTipShow(null, point, content, {classes: 'lm-tip-char', placement: 'bottom-start'});
}

function setUpHighlight(key) {
    const editor = tinymce.get(key);
    if (!editor) return;
    editor.on('selectionchange', function(e) {
        lmTipHide();

        var selected = editor.selection.getContent({ format: 'text' });
        if (!selected) return;

        // If it is not exactly #XX (where X are numbers) then exit
        selected = selected.trim();
        if (!/^[#@^]\d+$/.test(selected)) return;

        var win = editor.getWin();
        var sel = win.getSelection ? win.getSelection() : editor.getDoc().selection;
        if (!sel) return;

        var range = sel.rangeCount ? sel.getRangeAt(0) : null;
        if (range && !range.collapsed) {
            var rect = range.getBoundingClientRect();
            var iframeRect = editor.iframeElement.getBoundingClientRect();

            // Point below the middle of the selection, in viewport coordinates
            var x = rect.left + (rect.width / 2) + iframeRect.left;
            var y = rect.bottom + iframeRect.top;

            request = $.ajax({
                url: "{% url 'show_char' run.get_slug %}",
                method: "POST",
                data: { text: selected },
                datatype: "json",
            });

            request.done(function(res) {
                openCharTip(x, y, res.content);
            });
        }
    });
}

window.addEventListener('DOMContentLoaded', function() {
    $(document).ready(function(){
        {% for question in form.questions %}
            {% if question.typ == 'e' %}
                setUpHighlight('id_que_{{ question.uuid }}');
            {% elif question.typ == 'text' %}
                setUpHighlight('id_text');
            {% elif question.typ == 'teaser' %}
                setUpHighlight('id_teaser');
            {% endif %}
        {% endfor %}

        {% if form.add_char_finder %}
            {% for field in form.add_char_finder %}
                setUpHighlight('{{ field }}');
            {% endfor %}
        {% endif %}


    });

});

</script>
