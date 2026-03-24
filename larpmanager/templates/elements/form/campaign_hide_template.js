<script>
(function () {
    var parentField = $('#id_form1-parent');
    var templateRows = ['#id_form1-template_event_tr', '#id_form1-event_template_tr'];
    var templateFields = [
        { id: '#id_form1-template_event', isSelect2: true },
        { id: '#id_form1-event_template', isSelect2: false },
    ];

    function updateTemplateVisibility() {
        var hasParent = !!parentField.val();
        templateRows.forEach(function (rowId) {
            if ($(rowId).length) {
                if (hasParent) {
                    $(rowId).hide();
                } else {
                    $(rowId).show();
                }
            }
        });
        if (hasParent) {
            templateFields.forEach(function (f) {
                if ($(f.id).length) {
                    if (f.isSelect2) {
                        $(f.id).val(null).trigger('change');
                    } else {
                        $(f.id).val('');
                    }
                }
            });
        }
    }

    $(document).ready(function () {
        updateTemplateVisibility();
        parentField.on('change', updateTemplateVisibility);
    });
}());
</script>
