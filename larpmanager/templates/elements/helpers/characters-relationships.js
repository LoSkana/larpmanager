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

    function add_relationship(ch_id, ch_name) {

        charUrl = editUrl.replace(/\/0\/$/, `/${ch_id}/`);;

        var html = `
        <h3>
            <a href="{2}">{1}</a>
        </h3>
        <table >
            <tr>
                <th>{% trans "Direct" %}</th>
                <td>
                    <p>
                        <a href="#" class="my_toggle" tog="f_rel_{0}_direct">{% trans "Show" %}</a>
                    </p>
                    <div class="hide hide_later f_rel_{0}_direct">
                        <textarea name="rel_{0}" id="rel_{0}_direct"></textarea>
                    </div>
                    <div class="helptext">{% trans "How the relationship is described from this character's perspective" %}</div>
                </td>
            </tr>
        </table>
        `.format(ch_id, ch_name, charUrl);

        $('#form_relationships').prepend(html);

        window.addTinyMCETextarea('.f_rel_{0}_direct textarea'.format(ch_id)).then((editorId) => {
            setUpAutoSave(editorId);
            setUpCharFinder(editorId);
            setUpHighlight(editorId);
        });
        already.push(ch_id);

    }

    $(function() {
        {% for key, item in relationships.items %}
            window.addTinyMCETextarea('.f_{{ key }}_direct textarea').then((editorId) => {
                setUpAutoSave(editorId);
                setUpCharFinder(editorId);
                setUpHighlight(editorId);
            });
            already.push('{{ key }}');
        {% endfor %}

        document.getElementById('main_form').addEventListener('submit', function(e) {
            tinymce.triggerSave();
        });

        // add new
        $('#new_rel_select').on('select2:select select2:unselect change', function(e) {
            var value = $(this).val();
            if (value == null || value == '') return;

            if (value == eid) {
                alert('You have selected the character you are editing');
            }
            else if (already.includes(value)) {
                alert('Relationship with this character already exists');
            } else {
                var name = $(this).find('option:selected').text();
                add_relationship(value, name);
            }

            $(this).val(null).trigger('change');
        });
    });

});

</script>
