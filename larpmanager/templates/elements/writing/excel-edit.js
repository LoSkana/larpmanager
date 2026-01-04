{% load i18n %}

{% include "elements/writing/token.js" %}

<script>

window.addEventListener('DOMContentLoaded', function() {

    var keyTinyMCE;
    var qid;
    var eid;
    var workingTicketInterval = null;

    function closeEdit () {
        const x = window.scrollX;
        const y = window.scrollY;

        $('#excel-edit').removeClass('visible');
        if (keyTinyMCE) {
            editor = tinymce.get(keyTinyMCE);
            if (editor) {
                setTimeout(function() { editor.remove() }, 1000);

            }
            keyTinyMCE = null;
        }

        // Stop working ticket updates when closing the editor
        if (workingTicketInterval) {
            clearInterval(workingTicketInterval);
            workingTicketInterval = null;
        }

        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                window.scrollTo(x, y);
            });
        });

    }

    function callWorkingTicket() {
        if (!eid) return;

        $.ajax({
            type: "POST",
            url: "{% url 'working_ticket' %}",
            data: {eid: eid, type: '{{ label_typ }}', token: token},
            success: function(msg) {
                if (msg.warn) {
                    $.toast({
                        text: msg.warn,
                        icon: 'error',
                        position: 'mid-center',
                        textAlign: 'center',
                        allowToastClose: true,
                        hideAfter: false,
                        stack: 1
                    });
                }
            }
        });
    }

    // auto: if the function is called automatically to perform auto-save
    function submitExcelForm(auto) {
        // if auto, set timeout next invocation, and return if it's not visible
        if (auto) {
            setTimeout(() => submitExcelForm(auto), 15 * 1000);
            if (!$('#excel-edit').hasClass('visible')) return;
        }

        if (keyTinyMCE) {
            editor = tinymce.get(keyTinyMCE);
            if (editor) {
                tinymce.triggerSave();
            }
        }

        const form = document.getElementById('form-excel');
        const formData = new FormData(form);

        formData.append('eid', eid);
        formData.append('qid', qid);
        formData.append('auto', auto ? 1 : 0);
        formData.append('token', token);

        request = $.ajax({
            url: "{% url 'orga_writing_excel_submit' run.get_slug label_typ %}",
            method: "POST",
            data: formData,
            contentType: false,
            processData: false,
            datatype: "json",
        });

        request.done(function(res) {
            if (auto) {
                if (res.warn) {
                    $.toast({
                            text: res.warn,
                            showHideTransition: 'slide',
                            icon: 'error',
                            position: 'mid-center',
                            textAlign: 'center',
                            allowToastClose: true,
                            hideAfter: false,
                            stack: 1
                        });
                }
                return;
            }
            // server error
            if (res.k == 0) return;
            // success
            if (res.k == 1) {
                closeEdit();
                // Update DataTables instead of direct HTML manipulation
                Object.keys(window.datatables).forEach(function(key) {
                    const table = window.datatables[key];
                    // Try to find cell by class first (most common case)
                    let cell = table.cell('#' + res.eid, '.q_' + res.qid);

                    // If not found, try to find by qid attribute (for name and other special fields)
                    if (!cell || !cell.node()) {
                        const row = table.row('#' + res.eid);
                        if (row.length > 0) {
                            const rowNode = row.node();
                            const targetCell = $(rowNode).find('[qid="' + res.qid + '"]');
                            if (targetCell.length > 0) {
                                const cellIndex = targetCell.index();
                                cell = table.cell(rowNode, cellIndex);
                            }
                        }
                    }

                    if (cell && cell.node()) {
                        // Update cell HTML directly to preserve attributes
                        const cellNode = cell.node();
                        cellNode.innerHTML = res.update;
                        // Invalidate cell to sync DataTables internal state with DOM
                        cell.invalidate('dom');
                    }
                });
                return;
            }
            // form error
            alert(res.errors);
        });
    }

    $(function() {

        {% if auto_save %}
            submitExcelForm(true);
        {% endif %}

        // On double click on cell editable, start the single field edit
        $(document).on('dblclick', '.editable', function(event) {
            event.preventDefault();

            if ($("#main_bulk").is(":visible")) return;

            eid = $(this).parent().attr("id");
            qid = $(this).attr("qid");

            request = $.ajax({
                url: "{% url 'orga_writing_excel_edit' run.get_slug label_typ %}",
                method: "POST",
                data: { qid: qid, eid: eid},
                datatype: "json",
            });

            request.done(function(res) {
                if (res.k == 0) return;
                $('#excel-edit').empty().append(res.v);

                // Start working ticket updates every 1 second
                if (workingTicketInterval) {
                    clearInterval(workingTicketInterval);
                }
                callWorkingTicket(); // Call immediately
                workingTicketInterval = setInterval(callWorkingTicket, 1000);

                if (res.tinymce) {
                    window.addTinyMCETextarea('#excel-edit textarea').then((editorId) => {
                        keyTinyMCE = editorId;
                        setUpCharFinder(editorId);
                        setUpHighlight(editorId);
                    });
                }

                /*
                setTimeout(() => {
                    if (res.tinymce) {
                        // prepare tinymce count
                        prepare_tinymce(res.key, res.max_length);
                    }

                    // set up max length
                    if (res.max_length > 0) {
                        update_count(res.key, res.max_length, res.typ);
                        $('#' + res.key).on('input', function() {
                            update_count(res.key, res.max_length, res.typ);
                        });
                    }
                }, 100);
                */

                $('#excel-edit input[type="submit"]').on("click", function() {
                    submitExcelForm(false);
                });

                $('#excel-edit').addClass('visible');

                $('#excel-edit .close').on( "click", closeEdit );

            });
        });

        return false;
    });
});

</script>
