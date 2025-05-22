{% load tz show_tags static  i18n %}

<script>

var simple_count = ["t", "p", "name", "title"];
var multiple_count = ["m"];

var tm_done = [];

function tiny_count(editor, key) {
    const content = editor.getContent({ format: 'text' });
    const cl = content.length;
    $('#' + key + '_tr .count').html(cl);
}

// Add markers for #XX
function addMarkers(content) {
  const container = $('<div>').html(content);

  // Delete all span.marker
  container.find('span.marker').each(function () {
    $(this).replaceWith($(this).text());
  });

  // Create marker only #number
  container.contents().each(function processNode() {
    if (this.nodeType === 3) {
      let text = this.nodeValue;
      let parent = this.parentNode;

      if (!$(parent).is('span.marker')) {
        let replaced = text.replace(/#(\d+)(?!\d|\w)/g, '<span class="marker">#$1</span>');
        if (replaced !== text) {
          $(this).replaceWith(replaced);
        }
      }
    } else if (this.nodeType === 1 && !$(this).is('span.marker')) {
      $(this).contents().each(processNode);
    }
  });

  return container.html();
}

function updateEditorWithMarkers(editor) {
  const rng = editor.selection.getRng();
  const marker = document.createElement('span');
  marker.id = 'cursor-marker';
  marker.appendChild(document.createTextNode('\u200B')); // zero-width space
  rng.insertNode(marker);

  const content = editor.getContent();
  const newContent = addMarkers(content);

  editor.setContent(newContent);

  const newMarker = editor.getDoc().getElementById('cursor-marker');
  if (newMarker) {
    const range = editor.getDoc().createRange();
    range.setStartAfter(newMarker);
    range.collapse(true);
    const sel = editor.selection.getSel();
    sel.removeAllRanges();
    sel.addRange(range);
    newMarker.remove();
  }
}

function update_count(key, limit, typ) {
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
    } else {
        const editor = tinymce.get(key);

        if (editor) {
            // Count characters
              editor.on('input', () => {
                tiny_count(editor, key);

                var content = editor.getContent({ format: 'text' });
                  if (content.length > limit) {
                    const truncated = content.substring(0, MAX_CHARS);
                    editor.setContent(truncated);

                    editor.selection.select(editor.getBody(), true);
                    editor.selection.collapse(false);
                  } else {
                    updateEditorWithMarkers(editor);
                  }
              });

            // prevent to surpass max length
            editor.on('keydown', function (e) {
                const content = editor.getContent({ format: 'text' });
                const cl = content.length;
                const allowedKeys = [8, 37, 38, 39, 40, 46];
                if (cl >= limit && !allowedKeys.includes(e.keyCode)) {
                    e.preventDefault();
                } else {
                    updateEditorWithMarkers(editor);
                }


            });

            // prevent paste to surpass max length
            editor.on('paste', function (e) {
              const clipboard = (e.clipboardData || window.clipboardData).getData('text');
              var content = editor.getContent({ format: 'text' });
              if ((content.length + clipboard.length) >= limit) {
                e.preventDefault();
                const allowed = limit - content.length;
                if (allowed > 0) {
                  content = clipboard.substring(0, allowed);
                  editor.insertContent(content);
                }
              } else {
                updateEditorWithMarkers(editor);
              }

                tiny_count(editor, key);
            });
        }

        tiny_count(editor, key);
    }
}

window.addEventListener('DOMContentLoaded', function() {
    $(document).ready(function(){

        {% for key, args in form.max_lengths.items %}
            $('#' + '{{ key }}').on('input', function() {
                update_count('{{ key }}', {{ args.0 }}, '{{ args.1 }}');
            });
            update_count('{{ key }}', {{ args.0 }}, '{{ args.1 }}');
        {% endfor %}

    });

});

</script>
