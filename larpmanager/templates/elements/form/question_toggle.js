<script>

// placeholder shown on the selects of the questions that get hidden
var question_toggle_empty = '-------';

// Show or hide a whole question, given the field element of the question.
// A hidden question keeps no answer, and cannot block the submit: its inputs are
// cleared and the 'not-required' class marks the row for the mandatory check.
function toggle_question(el, visible) {
    if (!el.length) return;

    // the form templates wrap every field in a row with its own id, fall back to the ancestors
    var row = $('#' + el.attr('id') + '_tr');
    if (!row.length) row = el.parent().parent();

    // the question can be a single input, or a container of inputs (radio or checkbox groups)
    var inputs = el.find('input, select, textarea').addBack('input, select, textarea');

    if (visible) {
        row.show();
        el.prop('disabled', false);
        row.removeClass('not-required');
        // restore required attribute where it was originally set
        inputs.each(function () {
            if ($(this).data('was-required')) $(this).prop('required', true);
        });
        if (el.data('was-required')) el.prop('required', true);
        return;
    }

    row.hide();
    inputs.filter(':checkbox, :radio').prop('checked', false);
    el.find('option:selected').removeAttr('selected');
    if (el.is('select')) {
        var non = el.find('option:first');
        if (non.text() != question_toggle_empty)
            el.prepend('<option selected="true" disabled="disabled">' + question_toggle_empty + '</option>');
        else non.prop('selected', true);
        el.prop('disabled', true);
    }
    // remove required to prevent browser native validation on hidden fields
    inputs.each(function () {
        if ($(this).prop('required')) $(this).data('was-required', true);
        $(this).prop('required', false);
    });
    if (el.prop('required')) el.data('was-required', true);
    el.prop('required', false);

    row.addClass('not-required');
}

</script>
