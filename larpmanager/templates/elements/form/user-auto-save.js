{% load i18n %}

<script>

var lm_auto_save = {
    url: '{{ request.path }}',
    interval: 5 * 1000,
    timeout: 15 * 1000,
    stopped: false,
    running: false,
    last_data: null
};

function lmAutoSaveData() {
    if (window.tinyMCE && typeof tinyMCE.triggerSave === 'function') {
        tinyMCE.triggerSave();
    }
    return $('#main_form').serialize();
}

function lmAutoSaveFlash() {
    var submit = $('#form_submit');
    submit.addClass('auto_saved');
    setTimeout(function() {
        submit.removeClass('auto_saved');
    }, 1000);
}

function lmAutoSaveWarn(text) {
    $.toast({
        text: text,
        showHideTransition: 'slide',
        icon: 'error',
        position: 'mid-center',
        textAlign: 'center',
        allowToastClose: true,
        hideAfter: false,
        stack: 1
    });
}

function lmAutoSaveSubmit() {
    if (lm_auto_save.stopped || lm_auto_save.running) return;

    var data = lmAutoSaveData();

    // nothing changed since the last save
    if (data === lm_auto_save.last_data) return;

    // a new character is created only once it has a name
    if (!$('#base_updated').val() && !$.trim($('#id_name').val()).length) return;

    lm_auto_save.running = true;

    $.ajax({
        type: "POST",
        url: lm_auto_save.url,
        data: data + "&ajax=1",
        timeout: lm_auto_save.timeout
    }).done(function(msg) {
        if (!msg || msg.res !== 'ok') {
            if (msg && msg.stale) {
                lm_auto_save.stopped = true;
                lmAutoSaveWarn(msg.warn);
            }
            return;
        }

        lm_auto_save.last_data = data;
        $('#base_updated').val(msg.updated);

        // the character has just been created: keep on saving on its edit page
        if (msg.url) {
            lm_auto_save.url = msg.url;
            lm_auto_save.last_data = null;
            window.history.replaceState(null, '', msg.url);
            $('#main_form').attr('action', msg.url);
        }

        lmAutoSaveFlash();
    }).fail(function() {
        lmAutoSaveWarn('{% trans "Network or server error" %}');
    }).always(function() {
        lm_auto_save.running = false;
    });
}

window.addEventListener('DOMContentLoaded', function() {
    $(function() {
        // version stamp of the loaded element, to detect saves done from another window
        $('#main_form').append(
            $('<input>').attr({type: 'hidden', name: 'base_updated', id: 'base_updated'})
                        .val('{{ base_updated }}')
        );

        lm_auto_save.last_data = lmAutoSaveData();

        setInterval(lmAutoSaveSubmit, lm_auto_save.interval);

        $(document).keydown(function(event) {
            if (event.ctrlKey && event.key === 's') {
                event.preventDefault();
                lmAutoSaveSubmit();
            }
        });
    });
});

</script>
