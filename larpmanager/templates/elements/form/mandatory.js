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
    var missing = [];

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
        missing.push(k);
    }

    show_mandatory_summary(missing);

    if (first_error) {
        window.jump_to($('#mandatory-summary'));
        return false;
    }

    return true;
}

// Lists the unanswered mandatory questions at the top of the form, each linking to its field
function show_mandatory_summary(missing) {
    $('#mandatory-summary').remove();
    if (!missing.length) return;

    var list = $('<ul></ul>');
    $.each(missing, function(index, k) {
        var label = $.trim($('label[for="' + k + '"]').first().text()).replace(/:$/, '').replace(/\s*\(\*\)$/, '');
        var link = $('<a href="#" class="form-error-link"></a>').attr('data-field', k).text(label || k);
        list.append($('<li></li>').append(link));
    });

    var summary = $('<div id="mandatory-summary" class="form_error"></div>')
        .append($('<p></p>').text('{% filter escapejs %}{% trans "Missing reply in the following questions:" %}{% endfilter %}'))
        .append(list);

    var field = $('#' + missing[0]);
    var form = field.closest('form');
    if (form.length) form.prepend(summary);
    else field.closest('table').before(summary);
}
