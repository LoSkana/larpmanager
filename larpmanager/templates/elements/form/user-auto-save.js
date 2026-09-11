{% load i18n %}

<script>

var lm_auto_save = {
    url: '{{ request.path }}',
    form_id: '{{ auto_save_form_id|default:"main_form" }}',
    interval: 5 * 1000,
    timeout: 15 * 1000,
    // field that must be filled before a not-yet-created element is auto-saved for the first time;
    // empty when the form always edits an already existing element (no such gating needed)
    required_field: '{{ auto_save_required_field|default_if_none:"id_name" }}',
    running: false,
    last_data: null
};

function lmAutoSaveForm() {
    return $('#' + lm_auto_save.form_id);
}

function lmAutoSaveData() {
    if (window.tinyMCE && typeof tinyMCE.triggerSave === 'function') {
        tinyMCE.triggerSave();
    }
    return lmAutoSaveForm().serialize();
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
    if (lm_auto_save.running) return;

    var data = lmAutoSaveData();

    // nothing changed since the last save
    if (data === lm_auto_save.last_data) return;

    // a not-yet-created element is auto-saved only once its required field is filled
    if (!$('#base_updated').val() && lm_auto_save.required_field
        && !$.trim($('#' + lm_auto_save.required_field).val()).length) return;

    lm_auto_save.running = true;

    // stashes a staging draft server-side (redis, keyed by user + element); never writes the real record
    $.ajax({
        type: "POST",
        url: lm_auto_save.url,
        data: data + "&ajax=1",
        timeout: lm_auto_save.timeout
    }).done(function() {
        lm_auto_save.last_data = data;
    }).fail(function() {
        lmAutoSaveWarn('{% trans "Network or server error" %}');
    }).always(function() {
        lm_auto_save.running = false;
    });
}

function lmAutoSaveRestoreDraft(draftData) {
    var $form = lmAutoSaveForm();

    // clear checkbox/radio state first: the draft only carries pairs for checked ones
    $form.find('input:checkbox, input:radio').prop('checked', false);

    $.each(draftData.split('&'), function(index, pair) {
        if (!pair) return;
        var parts = pair.split('=');
        var name = decodeURIComponent(parts[0].replace(/\+/g, ' '));
        var value = decodeURIComponent((parts[1] || '').replace(/\+/g, ' '));
        var $field = $form.find('[name="' + name + '"]');
        if (!$field.length) return;

        if ($field.is(':checkbox, :radio')) {
            $field.filter('[value="' + value + '"]').prop('checked', true);
        } else {
            $field.val(value);
        }
        $field.trigger('change');
    });

    if (window.tinyMCE) {
        $.each(tinyMCE.editors, function(index, editor) {
            editor.load();
        });
    }

    var $banner = $('<div class="auto-save-draft-banner">')
        .append($('<span>').text('{% trans "An unsaved draft was restored. You can submit the form to confirm the changes, or reload the page to discard them." %}'))
        .append(
            $('<a href="#" class="auto-save-draft-dismiss" title="' + '{% trans "Dismiss" %}' + '">')
                .append($('<i class="fas fa-times">'))
        );
    $banner.find('.auto-save-draft-dismiss').on('click', function(event) {
        event.preventDefault();
        $banner.remove();
    });
    $('#banner').after($banner);
}

window.addEventListener('DOMContentLoaded', function() {
    $(function() {
        // version stamp of the loaded element, to detect saves done from another window
        lmAutoSaveForm().append(
            $('<input>').attr({type: 'hidden', name: 'base_updated', id: 'base_updated'})
                        .val('{{ base_updated }}')
        );

        var draftData = '{{ auto_save_draft|default:""|escapejs }}';
        if (draftData) {
            lmAutoSaveRestoreDraft(draftData);
        }

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
