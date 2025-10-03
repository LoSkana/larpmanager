{% include "elements/writing/token.js" %}

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
    return new Promise(function(resolve, reject) {
        if (eid == 0) {
            $.toast({
                text: 'Not available for new elements',
                showHideTransition: 'slide',
                icon: 'warning',
                position: 'top-center',
                textAlign: 'center',
                hideAfter: 1000
            });
            reject('no-eid');
            return;
        }

        if (window.tinyMCE && typeof tinyMCE.triggerSave === 'function') {
            tinyMCE.triggerSave();
        }

        var formData = $('form').serialize() + "&ajax=1";
        if (typeof eid !== 'undefined' && eid > 0) {
            formData += "&eid=" + eid + "&type=" + type + "&token=" + token;
        }

        $.ajax({
            type: "POST",
            url: post_url,
            data: formData,
            dataType: "json",
            timeout: timeout
        }).done(function(msg) {
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

            if (msg && (msg.warn || msg.error === true)) {
                $.toast({
                    text: msg.warn || 'Save failed',
                    showHideTransition: 'slide',
                    icon: 'error',
                    position: 'mid-center',
                    textAlign: 'center',
                    allowToastClose: true,
                    hideAfter: false,
                    stack: 1
                });
                reject('server-warn');
            } else {
                resolve(true);
            }
        }).fail(function(xhr) {
            $.toast({
                text: 'Network or server error',
                showHideTransition: 'slide',
                icon: 'error',
                position: 'mid-center',
                textAlign: 'center',
                allowToastClose: true,
                hideAfter: false,
                stack: 1
            });
            reject('ajax-fail');
        }).always(function() {
            setTimeout(()=>submitForm(true).catch(()=>{}), timeout);
        });
    });
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
    {% if auto_save %}
    if (eid != 0) {
        $(function() {
            submitForm(true);
        });
    }
    {% endif %}

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

    $('.trigger_save').on('click', function(e) {
        e.preventDefault();
        var href = $(this).attr('href');
        submitForm(false)
            .then(function() {
                window.location.href = href;
            })
            .catch(function() {
                // do nothing; stay on page
            });
    });
});

</script>
