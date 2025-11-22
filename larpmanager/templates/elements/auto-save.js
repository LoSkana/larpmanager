{% include "elements/writing/token.js" %}

<script>

{% if eid %}
var eid = {{ eid }};
{% else %}
var eid = 0;
{% endif %}
var type = '{{ type }}';

var timeout = 15 * 1000;
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
            timeout: timeout
        }).done(function(data, textStatus, xhr) {
            setTimeout(confirmSubmit, 100);

            // Try to parse JSON if it looks like JSON
            var msg = null;
            try {
                if (typeof data === 'string' && (data.trim().startsWith('{') || data.trim().startsWith('['))) {
                    msg = JSON.parse(data);
                } else if (typeof data === 'object') {
                    msg = data;
                }
            } catch (e) {
                console.log('Response is not valid JSON, treating as successful save');
            }

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
            // console.log('Auto-save failed:', xhr.status, xhr.statusText, xhr.responseText);
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

        // Validate href to prevent XSS and open redirect
        if (href && typeof href === 'string') {
            // Reject javascript:, data:, and other dangerous protocols
            var lowerHref = href.toLowerCase().trim();
            if (lowerHref.startsWith('javascript:') ||
                lowerHref.startsWith('data:') ||
                lowerHref.startsWith('vbscript:')) {
                console.error('Invalid href protocol detected');
                return;
            }

            // Only allow relative URLs or same-origin URLs
            if (!href.startsWith('/') && !href.startsWith('#')) {
                try {
                    var url = new URL(href, window.location.origin);
                    if (url.origin !== window.location.origin) {
                        console.error('Cross-origin redirect blocked');
                        return;
                    }
                } catch (e) {
                    console.error('Invalid URL');
                    return;
                }
            }
        } else {
            return;
        }

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
