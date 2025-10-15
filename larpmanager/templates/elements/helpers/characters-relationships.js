{% load i18n %}

<script>

const editUrl = "{% url 'orga_characters_edit' run.get_slug 0 %}";

{% if eid %}
    var eid = {{ eid }};
{% else %}
    var eid = null;
{% endif %}

// Get relationship length limit from form context
const relationshipLimit = {{ form.relationship_max_length }};

window.addEventListener('DOMContentLoaded', function() {

    var already = [];

    function setupRelationshipEditor(editorId) {
        setUpAutoSave(editorId);
        setUpCharFinder(editorId);
        setUpHighlight(editorId);
        setUpMaxLength(editorId, relationshipLimit, "text");
    }

    function add_relationship(ch_id, ch_name) {

        charUrl = editUrl.replace(/\/0\/$/, `/${ch_id}/`);;

        var html = `
        <h3>
            <a href="{2}">{1}</a>
        </h3>
        <table id="rel_{0}_tr">
            <tr>
                <th>{% trans "Direct" %}</th>
                <td>
                    <p>
                        <a href="#" class="my_toggle" tog="f_rel_{0}">{% trans "Show" %}</a>
                    </p>
                    <div class="hide hide_later f_rel_{0}">
                        <textarea name="rel_{0}" id="rel_{0}"></textarea>
                        <div class="helptext">
                            {% trans "text length" %}: <span class="count"></span> / {{ form.relationship_max_length }}
                        </div>
                    </div>
                    <div class="helptext">{% trans "How the relationship is described from this character's perspective" %}</div>
                </td>
            </tr>
        </table>
        `.format(ch_id, ch_name, charUrl);

        $('#form_relationships').prepend(html);

        window.addTinyMCETextarea('.f_rel_{0} textarea'.format(ch_id)).then((editorId) => {
            setupRelationshipEditor(editorId);
        });
        already.push(ch_id);

    }

    $(function() {
        {% for key, item in relationships.items %}
            window.addTinyMCETextarea('.f_{{ key }} textarea').then((editorId) => {
                setupRelationshipEditor(editorId);
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
