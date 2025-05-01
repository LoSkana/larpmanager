done = {};
down_all = false;

function load_que(index, first) {
    if (index >= regs.length) {
        setTimeout(check_download_all, 300);
        return;
    }

    num = regs[index];

    if (num in done) {
        load_que(index+1, true);
    } else {
        if (first) {
            $( '.lq_{0}'.format(num) ).trigger('click');
        }
        setTimeout(function() {
            load_que(index, false);
        }, 50);
    }

}

function load_question(el) {

    key = el.attr("key");

    if ($('.lq_{0}'.format(key)).hasClass('select')) {
        el.next().trigger('click');
        $( '.lq_{0}'.format(key) ).removeClass('select');
        return;
    }

    request = $.ajax({
        url: url_load_questions,
        data: { num: key },
        method: "POST",
        datatype: "json",
    });

    start_spinner();

    request.done(function(result) {

        num = result['num'];
        data = result['res'];
        const popup = new Set(result['popup']);

        for (let r in data) {
            let vl = data[r];
            if (vl.constructor === Array) vl = vl.join(", ");
            var vel = $('#{0} .res_{1}'.format(r, num));
            vel.text(vl);
            if (popup.has(parseInt(r)))
                vel.append("... <a href='#' class='post_popup' pop='{0}' fie='{1}'><i class='fas fa-eye'></i></a>".format(r, num));
        }

        el.next().trigger('click');

        $( '.lq_{0}'.format(key) ).addClass('select');

         done[num.toString()] = 1;

         stop_spinner();
    });

}

function load_question_email(el) {

    key = el.attr("key");

    if ($(".email_que_" + key + ":first").is(":visible")) {
        el.next().trigger('click');
        return;
    }

    request = $.ajax({
        url: url_load_questions_email,
        data: { num: key },
        method: "POST",
        datatype: "json",
    });

    start_spinner();

    request.done(function(data) {

        let t = '.email_que_{0} table tbody'.format(key)
        let tbl = $(t);
        tbl.empty();
        for (let nm in data) {
            let vl = data[nm];

            let txt = '<tr><td>{0}</td><td>{1}</td><td>{2}</td><td>{3}</td></tr>'.format(nm, vl.emails.length, vl.emails.join(", "), vl.names.join(", "));
            tbl.append(txt);
        }

        el.next().trigger('click');

        stop_spinner();
    });


}

function reload_table() {
    var resort = true, // re-apply the current sort
    callback = function() {
        // do something after the updateAll method has completed
    };

    // let the plugin know that we made a update, then the plugin will
    // automatically sort the table based on the header settings
    $("table").trigger("updateAll", [ resort, callback ]);
}

regs = [];

// first is true on first execution
function download_all(first) {

    down_all = true;

    if (first) {
        start_spinner();
        $( '.load_que' ).each(function() {
          regs.push($( this ).attr("key"));
        });
    }

    if (accounting) {
        if ('acc' in done) {
            load_que(0, true);
        } else {
            if (first) {
                $('#load_accounting').trigger('click');
            }
            setTimeout(function() {
                download_all(false);
            }, 50);
        }
    } else {
        load_que(0, true);
    }
}

function check_download_all() {

    all = true;

    if (accounting) {
        if (!('acc' in done)) all = false;
    }

    for (const num of regs) {
        if (!(num in done)) all = false;
    }

    if (all) {

        down_all = false;

        setTimeout(reload_table, 1000);

        $('.hide .question').show();
        $('.hide .acc').show();
        $('#load_accounting').addClass('select');
        $('.load_que').addClass('select');

        stop_spinner();

        $('.download_table tbody').empty();
        $('table.regs').each(function() {
            var rows = $(this).find('tbody tr').clone();
            $('.download_table tbody').append(rows);
            $('.download_table thead').empty();
            var rows = $(this).find('thead tr').clone();
            $('.download_table thead').append(rows);
        });

        $('.download_table .show_tooltip').remove();
        $('.download_table a').each(function() {
            if ($(this).text().trim() === "Manage") {
                $(this).remove();
            }
        });
        $('.download_table td, .download_table th').each(function() {
            var trimmedText = $(this).text().trim();
            var cleanedText = trimmedText.replace(/\t/g, '');
            $(this).text(cleanedText);
        });

        setTimeout(go_download_all, 1000);
    } else {
        setTimeout(check_download_all, 300);
    }
}

function go_download_all() {
    $('.go_table a').first().trigger('click');
}

function hide_download_link() {
    $('.go_table').hide();
}

window.addEventListener('DOMContentLoaded', function() {
    $(function() {

        $('.orga-buttons').append('<a id="download_all" class="button" href="#">' + download_text + '</a>');

        setTimeout(hide_download_link, 100);

        $('#download_all').on('click', function () {
            download_all(true);
            return false;
        });

        setTimeout(reload_table, 1000);

        $('.load_que').on('click', function () {
            load_question($(this));
            return false;
        });

        $('.load_email_que').on('click', function () {
            load_question_email($(this));
            return false;
        });

        $('.go_table a').hide();

    });

});
