{% if eid %}

<script>

var eid = {{ eid }};
var type = '{{ type }}';

var timeout = 10 * 1000;
var post_url = '{{ request.path }}';

function submitForm(auto) {
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
    $(function() {
        submitForm(true);
    });

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

{% else %}
    var eid = -1;
{% endif %}
