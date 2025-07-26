<script>

{% if eid %}
var eid = {{ eid }};
{% else %}
var eid = 0;
{% endif %}
var type = '{{ type }}';

var timeout = 10 * 1000;
var post_url = '{{ request.path }}';

function submitForm(auto) {
    if (eid == 0) {
        $.toast({
            text: 'Not available for new elements',
            showHideTransition: 'slide',
            icon: 'warning',
            position: 'top-center',
            textAlign: 'center',
            hideAfter: 1000
        });
        return;
    }
    tinyMCE.triggerSave();
    var formData = $('form').serialize() + "&ajax=1";
    if (typeof eid !== 'undefined' && eid > 0) {
        formData += "&eid=" + eid + "&type=" + type;
    }
    $.ajax({
        type: "POST",
        url: post_url,
        data: formData,
        success: function(msg) {
            if (msg.server_token != server_token) {
                $.toast({
                    text: 'Connection issue: please save and reload the page',
                    showHideTransition: 'slide',
                    icon: 'warning',
                    position: 'top-center',
                    textAlign: 'center',
                    hideAfter: 5000
                });
            }

            setTimeout(confirmSubmit, 100);
            if (!auto) {
                $.toast({
                    text: 'Saved!',
                    showHideTransition: 'slide',
                    icon: 'success',
                    position: 'top-center',
                    textAlign: 'center',
                    hideAfter: 1000
                });
            }
            if (msg.warn) alert(msg.warn);
        }
    });
    setTimeout(()=>submitForm(true), timeout);
}
function confirmSubmit() {
    $('#confirm').css('color', 'green');
    setTimeout(endConfirmSubmit, 1000);
}
function endConfirmSubmit() {
    $('#confirm').css('color', '');
}

function setUpAutoSave(key) {
    const editor = tinymce.get(key);
    if (!editor) return;
    editor.on('keydown', function(event) {
        if (event.ctrlKey && event.key === 's') {
            event.preventDefault();
            submitForm(false);
        }
    });
}

window.addEventListener('DOMContentLoaded', function() {
    if (eid != 0) {
        $(function() {
            submitForm(true);
        });
    }

    $(document).keydown(function(event) {
        if (event.ctrlKey && event.key === 's') {
            event.preventDefault();
            submitForm(false);
        }
    });

    {% for question in form.questions %}
        {% if question.typ == 'e' %}
            setUpAutoSave('id_q{{ question.id }}');
        {% elif question.typ == 'text' %}
            setUpAutoSave('id_text');
        {% elif question.typ == 'teaser' %}
            setUpAutoSave('id_teaser');
        {% endif %}
    {% endfor %}

    {% if form.add_char_finder %}
        {% for field in form.add_char_finder %}
            setUpAutoSave('{{ field }}');
        {% endfor %}
    {% endif %}
});
</script>
