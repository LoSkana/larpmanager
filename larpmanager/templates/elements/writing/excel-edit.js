{% load i18n %}

{{ TINYMCE_DEFAULT_CONFIG|json_script:"tinymce-config" }}

<script>

const tinymceConfig = JSON.parse(document.getElementById('tinymce-config').textContent);

window.addEventListener('DOMContentLoaded', function() {

    var keyTinyMCE;
    var qid;
    var eid;

    function closeEdit () {
        $('#excel-edit').removeClass('visible');
        if (keyTinyMCE) {
            editor = tinymce.get(keyTinyMCE);
            if (editor) {
                setTimeout(function() { editor.remove() }, 1000);

            }
            keyTinyMCE = null;
        }

    }

    function submitExcelForm() {
        if (keyTinyMCE) {
            editor = tinymce.get(keyTinyMCE);
            if (editor) {
                tinymce.triggerSave();
            }
        }
        formData = $('#form-excel').serialize();
        formData += '&eid=' + encodeURIComponent(eid) + '&qid=' + encodeURIComponent(qid);

        request = $.ajax({
            url: "{% url 'orga_writing_excel_submit' run.event.slug run.number label_typ %}",
            method: "POST",
            data: formData,
            datatype: "json",
        });

        request.done(function(res) {
            // server error
            if (res.k == 0) return;
            // success
            if (res.k == 1) {
                closeEdit();
                return;
            }
            // form error
            alert(res.errors);
        });
    }

    $(function() {

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
                $('#excel-edit input[type="submit"]').on( "click", submitExcelForm );
                $('#excel-edit').addClass('visible');

                $('#excel-edit .close').on( "click", closeEdit );
            });

            return false;
        });
    });
});

</script>
