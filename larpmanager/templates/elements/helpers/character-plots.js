{% load i18n %}

<script>

window.addEventListener('DOMContentLoaded', function() {

    var plotRoleHelp = '{{ form.plot_role_help_text|escapejs }}';

    function add_plot_role(plot_id, plot_name) {

        var html = `
        <tr id="id_pl_{0}_tr">
            <th>
                <label for="id_pl_{0}">{1}</label>
            </th>
            <td>
                <div class="hide  f_id_pl_{0}">
                    <textarea name="pl_{0}" id="id_pl_{0}"></textarea>
                </div>
                <p>
                    <a href="#" class="my_toggle" tog="f_id_pl_{0}">{% trans "Show" %}</a>
                </p>
                <div class="helptext">{2}</div>
            </td>
        </tr>
        `.format(plot_id, plot_name, plotRoleHelp.replace('%(name)s', plot_name));

        $('#id_plots_tr').parent().append(html);

        {% if not TINYMCE_DISABLED %}
        window.addTinyMCETextarea('.f_id_pl_{0} textarea'.format(plot_id)).then((editorId) => {
            if (typeof setUpAutoSave === 'function') setUpAutoSave(editorId);
            if (typeof setUpCharFinder === 'function') setUpCharFinder(editorId);
            if (typeof setUpHighlight === 'function') setUpHighlight(editorId);
        });
        {% endif %}
    }

    $(function() {

        var select = $('#id_plots');
        if (!select.length) return;

        var prevSelected = (select.val() || []).map(String);

        document.getElementById('main_form').addEventListener('submit', function(e) {
            if (window.tinymce) tinymce.triggerSave();
        });

        select.on('select2:select select2:unselect change', function(e) {
            var current = ($(this).val() || []).map(String);
            var prevSet = new Set(prevSelected);
            var currSet = new Set(current);

            // removed plots: keep the text in the dom, the row is dropped on save
            for (const id of prevSelected.filter(v => !currSet.has(v))) {
                $('#id_pl_' + id + '_tr').hide(300);
            }

            // added plots: bring back the existing row, or build it on the fly
            for (const id of current.filter(v => !prevSet.has(v))) {
                var row = $('#id_pl_' + id + '_tr');
                if (row.length) {
                    row.show(300);
                } else {
                    add_plot_role(id, $(this).find('option[value="' + id + '"]').text());
                }
            }

            prevSelected = current;
        });
    });

});

</script>
