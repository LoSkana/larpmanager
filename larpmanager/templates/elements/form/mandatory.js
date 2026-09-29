{% load i18n %}
function is_mandatory_empty(el) {
    if (el.is('div')) return !el.find('input:checked').length;
    if (el.is('input:checkbox, input:radio')) return !el.is(':checked');
    if (el.is('select')) {
        var val = el.val();
        return !val || (Array.isArray(val) && !val.length);
    }
    return !$.trim(el.val()).length;
}

// Marks every empty mandatory field, opens their sections and jumps to the first one
function check_mandatory_fields(mandatory, sections) {

    var first_error = null;

    for (var ix = 0; ix < mandatory.length; ix++) {
        var k = mandatory[ix];
        var el = $('#' + k);

        if (!el.length || el.attr('type') === 'hidden' || el.is('input:file')) continue;

        // hidden questions mark their own row, fall back to the ancestors
        var row = $('#' + k + '_tr');
        if (!row.length) row = el.parent().parent();
        if (row.hasClass('not-required')) continue;

        el.nextAll('.mandatory-error').remove();
        if (!is_mandatory_empty(el)) continue;

        var message = el.is('div, select')
            ? '{% filter escapejs %}{% trans "Please select a value" %}{% endfilter %}'
            : '{% filter escapejs %}{% trans "Please fill in this field" %}{% endfilter %}';
        el.after($('<p class="mandatory-error"><b class="form-error"></b></p>').find('b').text(message).end());
        el.off('.mandatory').one('change.mandatory input.mandatory', function() { $(this).nextAll('.mandatory-error').remove(); });

        if (sections && k in sections) $(".sec_" + slugify(sections[k])).show();
        if (!first_error) first_error = el;
    }

    if (first_error) {
        window.jump_to(first_error);
        return false;
    }

    return true;
}
