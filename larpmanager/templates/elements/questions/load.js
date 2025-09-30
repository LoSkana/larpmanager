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

    // Show spinner only after 500ms delay
    let spinnerTimeout = setTimeout(function() {
        if (!spinner) {
            start_spinner();
            spinner = true;
        }
    }, 500);

    request.done(function(result) {
        // Clear the spinner timeout since request completed
        clearTimeout(spinnerTimeout);

        num = result['num'];
        data = result['res'];
        const popup = new Set(result['popup']);

        el.next().trigger('click');

        // Batch updates by table to minimize DOM operations
        const tableUpdates = {};

        // Collect all updates first
        for (let r in data) {
            let vl = data[r];
            if (vl.constructor === Array) vl = vl.join(", ");

            if (popup.has(parseInt(r)))
                vl += "... <a href='#' class='post_popup' pop='{0}' fie='{1}'><i class='fas fa-eye'></i></a>".format(r, num);

            Object.keys(window.datatables).forEach(function(key) {
                const table = window.datatables[key];
                const row = table.row('#' + r);

                if (row.length > 0) {
                    if (!tableUpdates[key]) {
                        tableUpdates[key] = [];
                    }
                    tableUpdates[key].push({
                        rowSelector: '#' + r,
                        columnClass: '.q_' + num,
                        value: vl
                    });
                }
            });
        }

        // Apply all updates per table and draw once
        Object.keys(tableUpdates).forEach(function(key) {
            const table = window.datatables[key];
            const updates = tableUpdates[key];

            updates.forEach(function(update) {
                const cell = table.cell(update.rowSelector, update.columnClass);
                if (cell && cell.node()) {
                    cell.data(update.value);
                }
            });

            // Single draw call per table instead of multiple
            table.draw(false);
        });

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

    // Show spinner only after 500ms delay
    let spinnerTimeout = setTimeout(function() {
        start_spinner();
    }, 500);

    request.done(function(data) {
        // Clear the spinner timeout since request completed
        clearTimeout(spinnerTimeout);

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

window.hideColumnsIndexMap = {};
document.querySelectorAll('.que_load thead th').forEach(function(th) {
    var realIndex = Array.from(th.parentNode.children).indexOf(th);
    th.classList.forEach(function(cls) {
        if (!window.hideColumnsIndexMap[cls]) {
            window.hideColumnsIndexMap[cls] = [];
        }
        if (!window.hideColumnsIndexMap[cls].includes(realIndex)) {
            window.hideColumnsIndexMap[cls].push(realIndex);
        }
    });
});

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

        $('.table_toggle').on('click', function () {
            var tog = $(this).attr("tog");
            $(this).toggleClass('select');

            var index_list = window.hideColumnsIndexMap[tog];
            Object.keys(window.datatables).forEach(function(key) {
                var table = window.datatables[key];

                for (const index of index_list) {
                    var column = table.column(index);
                    column.visible(!column.visible());
                };
            });

            return false;
        });

    });

});
