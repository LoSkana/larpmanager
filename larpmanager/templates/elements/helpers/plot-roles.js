{% load i18n %}

<script>

const editUrl = "{% url 'orga_characters_edit' run.event.slug run.number 0 %}";

{% if eid %}
    var eid = {{ eid }};
{% else %}
    var eid = null;
{% endif %}

window.addEventListener('DOMContentLoaded', function() {

    var already = [];

    function add_role(ch_id, ch_name) {

        console.log(ch_id);
        console.log(ch_name);

        charUrl = editUrl.replace(/\/0\/$/, `/${ch_id}/`);;

        var html = `
        <tr id="id_char_role_{0}_tr">
            <th>
                <a href="{2}"><label>{1}</label></a>
            </th>
            <td>
                <p>
                    <a href="#" class="my_toggle" tog="f_ch_{0}">{% trans "Show" %}</a>
                </p>
                <div class="hide hide_later f_ch_{0}">
                    <textarea name="char_role_{0}" id="ch_{0}"></textarea>
                </div>
                <div class="helptext">{{ form.role_help_text }} {1}</div>
            </td>
        </tr>
        `.format(ch_id, ch_name, charUrl);

        $('#main_form table tbody').append(html);

        window.addTinyMCETextarea('.f_ch_{0} textarea'.format(ch_id)).then((editorId) => {
            setUpAutoSave(editorId);
            setUpCharFinder(editorId);
            setUpHighlight(editorId);
        });
        already.push(ch_id);

    }

    $(function() {
        let prevSelected = ($("#id_characters").val() || []).map(String);

        document.getElementById('main_form').addEventListener('submit', function(e) {
            tinymce.triggerSave();
        });

        // add new
        $('#id_characters').on('select2:select select2:unselect change', function(e) {
            var value = $(this).val();

            const $sel = $(this);
            const current = ($sel.val() || []).map(String);

            // build lookup sets
            const prevSet = new Set(prevSelected);
            const currSet = new Set(current);

            // diffs
            const removed = prevSelected.filter(id => !currSet.has(id));
            const added   = current.filter(id => !prevSet.has(id));

            // handle removed: hide rows
            for (const id of removed) {
                el = $('#id_char_role_' + id + '_tr');
                el.hide(300);
            }

            // handle added: show existing or create new
            for (const id of added) {
                key = '#id_char_role_' + id + '_tr';
                const $row = $(key);
                if ($row.length) {
                    $(key).show(300);
                } else {
                    const name = $sel.find('option[value="' + id +'"').text();
                    add_role(id, name);
                }
            }

            // update selected
            prevSelected = current;
        });
    });

});

</script>
