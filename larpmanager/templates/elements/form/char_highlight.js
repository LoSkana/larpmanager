{% load tz show_tags static  i18n %}

<script>

var tinymce_count = ["teaser", "text", "e"];

function openQtip(pageX, pageY, x, y, content) {
    $('body').append('<div id="qtip-cursor-helper" style="position:absolute;left:' + pageX + 'px;top:' + pageY + 'px;width:1px;height:1px;"></div>');
    $('#qtip-cursor-helper').qtip({
        content: { text: content },
        style: {
            classes: 'qtip-dark qtip-rounded qtip-shadow'
        }, show: {
            ready: true,
            effect: function(offset) {
                $(this).fadeIn(500);
            }
        }, hide: {
            event: 'mouseleave unfocus click',
            delay: 200,
            effect: function(offset) {
                $(this).fadeOut(500);
            }
        }, position: {
            my: 'top left',
            at: 'bottom center',
            target: [x, y]
        }, events: {
            hide: function() {
                $('#qtip-cursor-helper').remove();
            }
        }
    });
}

function setUpHighlight(key) {
    const editor = tinymce.get(key);
    if (!editor) return;
    editor.on('selectionchange', function(e) {
        $('#qtip-cursor-helper').remove();
        $('.qtip').qtip('hide');

        var selected = editor.selection.getContent({ format: 'text' });
        if (!selected) return;

        // If it is not exactly #XX (where X are numbers) then exit
        selected = $.trim(selected);
        if (!/^[#@^]\d+$/.test(selected)) return;

        var win = editor.getWin();
        var sel = win.getSelection ? win.getSelection() : editor.getDoc().selection;
        if (!sel) return;

        var range = sel.rangeCount ? sel.getRangeAt(0) : null;
        if (range && !range.collapsed) {
            var rect = range.getBoundingClientRect();
            var iframeRect = editor.iframeElement.getBoundingClientRect();

            // Scroll in iframe
            var iframeScroll = editor.getDoc().documentElement.scrollTop || editor.getDoc().body.scrollTop;

            // Scroll in page
            var pageScrollY = window.scrollY || window.pageYOffset;
            var pageScrollX = window.scrollX || window.pageXOffset;

            // Final computation
            var pageX = rect.left + iframeRect.left + pageScrollX;
            var pageY = rect.top + iframeRect.top + pageScrollY + iframeScroll;
            var x = rect.left + (rect.width / 2) + iframeRect.left + pageScrollX;
            var y = rect.bottom + iframeRect.top + pageScrollY + iframeScroll;

            // console.log('Page X:', pageX, 'Page Y:', pageY);
            // console.log('x:', x, 'y:', y);

            request = $.ajax({
                url: "{% url 'show_char' event.slug run.number %}",
                method: "POST",
                data: { text: selected },
                datatype: "json",
            });

            request.done(function(res) {
                openQtip(pageX, pageY, x, y, res.content);
            });
        }
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

        {% if form.add_char_finder %}
            {% for field in form.add_char_finder %}
                setUpHighlight('{{ field }}');
            {% endfor %}
        {% endif %}

    });

});

</script>
