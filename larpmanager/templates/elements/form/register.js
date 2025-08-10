{% load tz show_tags static  i18n %}

<script>

var unavail = {{ form.unavail }};

var hide_unavailable = {{ hide_unavailable | yesno:"true,false" }};

{% if not gift %}

    var discount_url = '{% url "discount" event.slug run.number %}';
    var discount_list_url  = '{% url "discount_list" event.slug run.number %}';

    var discount_apply = '{{ discount_apply }}';

{% endif %}

var mandatory = {{ form.mandatory | safe }};

var sections = {{ form.sections | safe }};

var tokens = parseLocalNum("{{ member.tokens }}");
var credit = parseLocalNum("{{ member.credit }}");
var tot_payed = parseLocalNum("{{ tot_payed }}");

var tickets_map = {{ form.tickets_map | safe }};

var ticket_price = {% if form.ticket_price %}{{ form.ticket_price }}{% else %}0{% endif %};

function parseLocalNum(num) {
    return +(num.replace(",", "."));
}

var submitted = {{ submitted | safe }};

 var price_regex = /(\d+(?:\.\d+)?){{ currency_symbol }}/g;

 function get_price(s) {
     found = s.match(price_regex);
            if (!found) return 0;
    v = parseFloat(found[0].replace("{{ currency_symbol }}", ""));
    return v;
 }

 function grey_poor(k) {
    k = '#id_' + k;
    var def = $(k + ' option:selected');
    var v = get_price(def.text());
    if (v == 0) return;
    var kk = def.attr('value');
    $(k + ' option').each(function(index, value) {
        var w = get_price($(this).text());
        if (w < v) $(this).attr('disabled','disabled');
    });

 }

var diss = '-------';

window.addEventListener('DOMContentLoaded', function() {
$(document).ready(function(){

    if (!("ticket" in submitted) || !(submitted["ticket"])) {
        // force to select a ticket if not selected
        var dis = $('#id_ticket option').length == 1;
        $('#confirm').prop('disabled', !dis);
    }

    Object.entries(unavail).forEach(([question, values]) => {
        // console.log(question);
        // console.log(values);
        values.forEach(value => {
            const selectorPrefix = '#id_q' + question + '_tr ';
            if (hide_unavailable) {
                $(selectorPrefix + 'option[value="' + value + '"]').remove();
                $(selectorPrefix + 'input[type="checkbox"][value="' + value + '"]').closest('label').remove();
            } else {
                $(selectorPrefix + 'option[value="' + value + '"]').prop("disabled", true);
                $(selectorPrefix + 'input[type="checkbox"][value="' + value + '"]')
                    .prop("disabled", true)
                    .addClass("unavail");
            }
        });
    });

    for (const el of ['id_quotas', 'id_ticket', 'id_additionals']) {
        if ( $( "#" + el ).length ) mandatory.unshift(el);
    }

    $('select').each(function(index, value) {
        var nm = $(this).attr('id').replace("id_", "");

        // skip in only one option
        if ($(this).find('option').length == 1) return;

        // skip if the value was submitted in a previous POST
        if ((nm in submitted) && submitted[nm]) return;

        $(this).prepend('<option selected="true" disabled="disabled">' + diss + '</option>');
    });

    {% if payment_lock %}
        $('select').each(function(index, value) {
            var nm = $(this).attr('id').replace("id_", "");
            grey_poor(nm);
        });
    {% endif %}

    $('select,input').on('change', function() {
        $('#riepilogo').hide(500);
    });

    $('#confirm').on('click', function() {
        if (!check_mandatory()) return;

        var s = $('select[name =\"signup\"] option:selected').val();

        var sum = ticket_price;
        $('select').each(function(index, value) {
           var sel = $(this).val();
           if ( !sel ) return;
           var text = $(this).find(":selected").text();
           sum += get_price(text);
        });

        $('input:checked').each(function () {
           sum += get_price($(this).parent().text());
        });

        $('#id_pay_what').each(function(index, value) {
           sum += parseInt($(this).val()) || 0;
        });

        $('.discount_ac').each(function(index, value) {
           sum -= parseInt($(this).html());
        });

        total = sum;

        if (tot_payed > 0) {
            sum = Math.max(0, sum - tot_payed);
        }
        var credit_u = 0;
        if (credit > 0) {
            credit_u = Math.min(sum, credit);
            sum -= credit_u;
        }
        var token_u = 0;
        if (tokens > 0) {
            token_u = Math.min(sum, tokens);
            sum -= token_u;
        }

        $('#riepilogo table .riep').remove();

        tx = "";

        if (total > 0)
            tx += "<tr class='riep'><td>" + window['texts']['upd'] + ": <b>" + total + "{{ currency_symbol }}</b>.";

        if (tot_payed > 0)
            tx += " " + "" + window['texts']['alr'] + ": <b>" + tot_payed + "{{ currency_symbol }}</b>.";
        if (credit_u > 0)
            tx += " " + "" + window['texts']['cre'] + ": <b>" + credit_u + "</b>.";
        if (token_u > 0)
            tx += " " + "" + window['texts']['tok'] + ": <b>" + token_u + "</b>.";

        tx += "</td></tr>";

        if (window['texts']['payment'] && sum > 0 && tot_payed == 0)
            tx += "<tr class='riep'><td>" + window['texts']['pro'] + "</td></tr>";

        $('#riepilogo table > tbody:first-child > tr:first-child').after(tx);

        if ($('#riepilogo table tr').length === 1) {
            $('#register_go').click();
        } else {
            $('#riepilogo').show(200);
            setTimeout(() => jump_to($('#riepilogo')), 300);
        }
    });

    $('select').on('change', function() {
        $('#riepilogo').hide(500);
    });

    {% if not gift %}

        {% if features.discount and 'waiting' not in run.status %}

            show_discount_list();

            if (discount_apply.length > 0) {
                $('#id_discount').val(discount_apply)
                discount_go();
            }

        {% endif %}

        $('#discount_go').on('click', function() {
            $('#riepilogo').hide(500);
            try { discount_go();} catch (e) { console.log(e.message);}
            return false;
        });

    {% endif %}

    $('#id_ticket').on('change', function() {
        $('#confirm').prop('disabled', false);
        check_tickets_map();
    });

    check_tickets_map();



});

function slugify(text) {
  return text
    .toString()
    .normalize('NFKD')             // normalizza caratteri Unicode
    .replace(/[\u0300-\u036f]/g, '') // rimuove segni diacritici
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9 -]/g, '')    // rimuove caratteri non validi
    .replace(/\s+/g, '-')           // sostituisce spazi con -
    .replace(/-+/g, '-');           // rimuove ripetizioni di -
}

function check_mandatory() {

    for (var ix = 0; ix < mandatory.length; ix++) {
        var k = mandatory[ix];
        var el = $('#' + k);

        if (el.attr('type') === 'hidden') continue;

        if (el.parent().parent().hasClass('not-required')) continue;

        empty = true;
        if (el.is('input:text')) {
            empty = (!$.trim(el.val()).length);
        } else if (el.is('select')) {
            empty = (!el.val());
        } else if (el.is('textarea')) {
            empty = (!$.trim(el.val()));
        } else if (el.is('div')) {
            empty = (!el.find('input:checked').length)
        }

        el.next('p').remove();
        if (empty) {
            el.after( "<p><b class='form-error' style='color: var(--ter-clr);'>Please select a value</b></p>" );
            if (k in sections) $(".sec_" + slugify(sections[k])).show();
            window.jump_to($('#' + k));
            return false;
        }
    }

    return true;

}






function check_tickets_map() {
    // get selected ticket
    var sel = $('#id_ticket').val();
    if( !sel ) sel = 0;

    $.each(tickets_map, function(index, value) {
        var f = $.inArray(parseInt(sel), value) !== -1;
        var el = $('#id_' + index);

        if (f) {
            // show the question
            el.parent().parent().show();
            el.prop('disabled', false);
            el.parent().parent().removeClass('not-required');
        } else {
            // hide the question
            el.parent().parent().hide();
            $('#id_' + index + ' :checkbox').prop( "checked", false );
            $('#id_' + index + ' option:selected').removeAttr("selected");
            if (el.is('select')) {
                var non = el.find("option:first")
                if (non.text() != diss)
                    el.prepend('<option selected="true" disabled="disabled">' + diss + '</option>');
                else non.prop('selected', true);
                el.prop('disabled', true);
            }

            el.parent().parent().addClass('not-required');
        }
    });

    if (sel == 0) return;
    $('table.section').each(function(index, value) {
        section = $(this).attr("section");

        if ($(this).find('tr:not(.not-required)').length == 0) {
            $('.sec_' + section).hide();
            $('.head_' + section).hide();
        } else {
            $('.head_' + section).show();
        }
    });
}

$('#register_go').on('click', function() {

    if (!check_mandatory()) return false;

    $('input:checked').each(function () {
        $(this).prop('disabled', false);
    });

    return true;
});

{% if not gift %}

function show_discount_list(rep=true) {

    $.get({
        url: discount_list_url,
        success: function(data) {

            var vel = $('#discount_riep');
            var rowCount = $('#discount_tbl tr').length;
            $('#discount_tbl tr:gt(0)').remove();
            for (var i = 0; i < data.lst.length; i++) {
                var el = data.lst[i];

                $('#discount_tbl tr:last').after('<tr><td>{0}</td><td><span class="discount_ac">{1}</span>{{ currency_symbol }}</td><td>{2}</td></tr>'.format(el.name, el.value, el.expires));
            }

            if (data.lst.length == 0) { vel.hide(200); return; }
            vel.show(200);

            if (rowCount != $('#discount_tbl tr').length)
                $('#riepilogo').hide(500);
        }
    });

    if (rep) setTimeout(show_discount_list, 60000);
}

function discount_go() {

    var csrftoken = $('input[name="csrfmiddlewaretoken"]').val();

    var data = {cod: $('#id_discount').val(), 'csrfmiddlewaretoken': csrftoken};

    $.ajax({
        type: "POST",
        url: discount_url,
        data: data,
        success: function(data) {
            $('#id_discount').val("")

            var el = $('#discount_res');
            el.html(data.msg);
            el.show(200);
            if (data.res != "ok") { setTimeout(function() { el.hide(500); }, 2000);  el.removeClass('success'); return; }

            setTimeout(function() { el.hide(500); }, 10000);
            el.addClass('success');
            show_discount_list(false);
        }
    });
}

{% endif %}

});

</script>
