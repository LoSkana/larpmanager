done = {};
down_all = false;

spinner = false;

function load_que(index, first) {
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

    $( '.lq_{0}'.format(key) ).addClass('select');

    request = $.ajax({
        url: url_load_questions,
        data: { num: key },
        method: "POST",
        datatype: "json",
    });

    if (!spinner) {
        start_spinner();
        spinner = true;
    }

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

        window.syncColumnWidths();

         done[num.toString()] = 1;

         if (spinner) {
            stop_spinner();
            spinner = false;
        }
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

window.addEventListener('DOMContentLoaded', function() {
    $(function() {

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

        if (Array.isArray(window.trigger_togs)) {
            window.trigger_togs.forEach(function(togValue) {
                if (togValue.startsWith('.') || togValue.startsWith('#')) {
                    $(togValue).each(function() {
                        this.dispatchEvent(new MouseEvent('click', { bubbles: true }));
                    });
                }
            });
        }

    });

});
