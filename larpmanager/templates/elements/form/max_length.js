{% load tz show_tags static  i18n %}

<script>

var simple_count = ["t", "p", "name", "title"];
var multiple_count = ["m"];
var tinymce_count = ["teaser", "text", "e"];

var tm_done = [];

function tiny_count(editor, key) {
    const content = editor.getContent({ format: 'text' });
    const cl = content.length;
    $('#' + key + '_tr .count').html(cl);
}

function prepare_tinymce(key, limit) {
  const editor = tinymce.get(key);
    if (editor) {
    // Count characters
      editor.on('input', () => {
        tiny_count(editor, key);

        const content = editor.getContent({ format: 'text' });
          if (content.length > limit) {
            const truncated = content.substring(0, limit);
            editor.setContent(truncated);

            editor.selection.select(editor.getBody(), true);
            editor.selection.collapse(false);
          }
      });

    // prevent to surpass max length
    editor.on('keydown', function (e) {
        const content = editor.getContent({ format: 'text' });
        const cl = content.length;
        const allowedKeys = [8, 37, 38, 39, 40, 46];
        if (cl >= limit && !allowedKeys.includes(e.keyCode)) {
            e.preventDefault();
        }
    });

    // prevent paste to surpass max length
    editor.on('paste', function (e) {
        const clipboard = (e.clipboardData || window.clipboardData).getData('text');
        const content = editor.getContent({ format: 'text' });
        if ((content.length + clipboard.length) >= limit) {
            e.preventDefault();
            const allowed = limit - content.length;
            if (allowed > 0) {
                editor.insertContent(clipboard.substring(0, allowed));
            }
        }

        tiny_count(editor, key);
    });

  }
}

function update_count(key, limit, typ, loop) {
    var el = $('#' + key);
    if (simple_count.includes(typ)) {
        cl = el.val().length;
        el.parent().find(".count").html(cl);
        if (cl > limit) {
            el.val(el.val().substring(0, limit));
            el.parent().find(".count").html(limit);
        }
    } else if (multiple_count.includes(typ)) {
        var name = key.replace(/^id_/, '');
        var group = $('input[name="' + name + '"]');
        var checkedCount = group.filter(':checked').length;
        group.not(':checked').not('.unavail').prop('disabled', checkedCount >= limit);
        el.parent().find(".count").html(checkedCount);
    } else if (tinymce_count.includes(typ)) {
        const editor = tinymce.get(key);
        tiny_count(editor, key);
    }

    if (loop) {
        setTimeout(
            ()=> update_count(key, limit, typ, loop),
            1000
        );
    }
}

window.addEventListener('DOMContentLoaded', function() {
    $(document).ready(function(){

        {% for key, args in form.max_lengths.items %}
            $('#' + '{{ key }}').on('input', function() {
                update_count('{{ key }}', {{ args.0 }}, '{{ args.1 }}');
            });
            update_count('{{ key }}', {{ args.0 }}, '{{ args.1 }}', true);

            if (tinymce_count.includes('{{ args.1 }}'))
                prepare_tinymce('{{ key }}', {{ args.0 }});
        {% endfor %}

    });

});

</script>
