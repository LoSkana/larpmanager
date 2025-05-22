{% load tz show_tags static  i18n %}

<script>

var tinymce_count = ["teaser", "text", "e"];

function setUpHighlight(key) {
    const editor = tinymce.get(key);
    if (!editor) return;
    editor.on('selectionchange', function(e) {
        var selected = editor.selection.getContent({ format: 'text' });
        if (!selected) return;

        // If it is not exactly #XX (where X are numbers) then exit
        if (!/^#\d+$/.test($(element).text())) return;

        var win = editor.getWin();
        var sel = win.getSelection ? win.getSelection() : editor.getDoc().selection;
        if (!sel) return;

        var range = sel.rangeCount ? sel.getRangeAt(0) : null;
        if (range && !range.collapsed) {
            var rect = range.getBoundingClientRect();
            var iframeRect = editor.iframeElement.getBoundingClientRect();
            var pageX = rect.left + iframeRect.left;
            var pageY = rect.top + iframeRect.top;
            console.log('Page X:', pageX, 'Page Y:', pageY);
        }

        console.log(selected);
    });
}

window.addEventListener('DOMContentLoaded', function() {
    $(document).ready(function(){
        {% for question in form.questions %}
            {% if question.typ == 'e' %}
                setUpHighlight('id_q{{ question.id }}');
            {% elif question.typ == 'text' %}
                setUpHighlight('id_text');
            {% elif question.typ == 'teaser' %}
                setUpHighlight('id_teaser');
            {% endif %}
        {% endfor %}

    });

});

</script>
