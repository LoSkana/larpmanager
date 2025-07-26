{% load i18n %}

<script>

const tinymceConfig = JSON.parse(document.getElementById('tinymce-config').textContent);

window.addEventListener('DOMContentLoaded', function() {

    var keyTinyMCE;
    var qid;
    var eid;

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

        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                window.scrollTo(x, y);
            });
        });

    }

    // auto: if the function is called automatically to perform auto-save
    function submitExcelForm(auto) {
        // if auto, set timeout next invocation, and return if it's not visible
        if (auto) {
            setTimeout(() => submitExcelForm(auto), 10 * 1000);
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

        request = $.ajax({
            url: "{% url 'orga_writing_excel_submit' run.event.slug run.number label_typ %}",
            method: "POST",
            data: formData,
            contentType: false,
            processData: false,
            datatype: "json",
        });

        request.done(function(res) {
            if (auto) {
                if (res.warn) alert(res.warn);
                return;
            }
            // server error
            if (res.k == 0) return;
            // success
            if (res.k == 1) {
                closeEdit();
                $('#' + res.eid + ' [qid=' + res.qid + ']').html(res.update);
                return;
            }
            // form error
            alert(res.errors);
        });
    }

    $(function() {

        submitExcelForm(true);

        // On double click on cell editable, start the single field edit
        $(document).on('dblclick', '.editable', function(event) {
            event.preventDefault();

            eid = $(this).parent().attr("id");
            qid = $(this).attr("qid");

            request = $.ajax({
                url: "{% url 'orga_writing_excel_edit' run.event.slug run.number label_typ %}",
                method: "POST",
                data: { qid: qid, eid: eid },
                datatype: "json",
            });

            request.done(function(res) {
                if (res.k == 0) return;

                if (res.server_token != server_token) {
                    $.toast({
                        text: 'Connection issue: please reload the page',
                        showHideTransition: 'slide',
                        icon: 'warning',
                        position: 'top-center',
                        textAlign: 'center',
                        hideAfter: 5000
                    });
                    return;
                }

                $('#excel-edit').empty().append(res.v);

                if (res.tinymce) {
                    let config = Object.assign({}, tinymceConfig);
                    config.selector = '#excel-edit textarea' + ':not(.tinymce-initialized)';
                    config.setup = function (editor) {
                        editor.on('init', function () {
                            editor.getElement().classList.add('tinymce-initialized');
                            keyTinyMCE = editor.id;
                        });
                    };
                    tinymce.init(config);
                }

                setTimeout(() => {
                    if (res.tinymce) {
                        // set up char highlight
                        setUpHighlight(keyTinyMCE);

                        // set up char finder
                        setUpCharFinder(keyTinyMCE);

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
