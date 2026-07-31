{% load i18n %}

<script>

const editUrl = "{% url 'orga_characters_new' run.get_slug %}";

{% if edit_uuid %}
    var edit_uuid = '{{ edit_uuid }}';
{% else %}
    var edit_uuid = '';
{% endif %}

// Get relationship length limit from form context
const relationshipLimit = {{ form.relationship_max_length|default:10000 }};

// Relationship tags available in this event, used to build the tags checkboxes for newly added relationships
const relationshipTags = [
    {% for tag in relationship_tags %}
        {uuid: "{{ tag.uuid|escapejs }}", name: "{{ tag.name|escapejs }}"},
    {% endfor %}
];

window.addEventListener('DOMContentLoaded', function() {

    var already = [];

    function setupRelationshipEditor(editorId) {
        setUpAutoSave(editorId);
        setUpCharFinder(editorId);
        setUpHighlight(editorId);
        setUpMaxLength(editorId, relationshipLimit, "text");
    }

    function add_relationship(ch_uuid, ch_name) {

        charUrl = editUrl.replace(/\/0\/$/, `/${ch_uuid}/`);;

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
                    <div class="hide  f_rel_{0}">
                        <textarea name="rel_{0}" id="rel_{0}"></textarea>
                        <div class="helptext">
                            {% trans "text length" %}: <span class="count"></span> / {{ form.relationship_max_length }}
                        </div>
                    </div>
                    <div class="helptext">{% trans "How the relationship is described from this character's perspective" %}</div>
                </td>
            </tr>
        </table>
        `.format(ch_uuid, ch_name, charUrl);

        $('#form_relationships').prepend(html);

        {% if not TINYMCE_DISABLED %}
        window.addTinyMCETextarea('.f_rel_{0} textarea'.format(ch_uuid)).then((editorId) => {
            setupRelationshipEditor(editorId);
        });
        {% endif %}

        if (relationshipTags.length) {
            var tagsCell = $('<td class="tags_cell"></td>');
            relationshipTags.forEach(function(tag) {
                // build with DOM nodes: tag names are organizer-supplied and must never be parsed as HTML
                var checkbox = $('<input type="checkbox">')
                    .attr('name', 'rel_tags_' + ch_uuid)
                    .attr('value', tag.uuid);
                tagsCell.append($('<label class="rel_tag_checkbox"></label>').append(checkbox).append(document.createTextNode(tag.name)));
            });
            {% trans "Tags" as tags_label %}
            {% trans "Symmetric tags apply to both characters in the relationship" as tags_helptext %}
            tagsCell.append($('<div class="helptext"></div>').text("{{ tags_helptext|escapejs }}"));
            var tagsRow = $('<tr></tr>').append($('<th></th>').text("{{ tags_label|escapejs }}")).append(tagsCell);
            $('#rel_' + ch_uuid + '_tr').append(tagsRow);
        }

        already.push(ch_uuid);

    }

    $(function() {
        {% for key, item in relationships.items %}
            {% if not TINYMCE_DISABLED %}
            window.addTinyMCETextarea('.f_{{ key }} textarea').then((editorId) => {
                setupRelationshipEditor(editorId);
            });
            {% endif %}
            already.push('{{ key }}');
        {% endfor %}

        document.getElementById('main_form').addEventListener('submit', function(e) {
            {% if not TINYMCE_DISABLED %}
            tinymce.triggerSave();
            {% endif %}
        });

        // add new
        $('#new_rel_select').on('select2:select select2:unselect change', function(e) {
            var value = $(this).val();
            if (value == null || value == '') return;

            if (value == edit_uuid) {
                if (!window.lmTesting) alert('You have selected the character you are editing');
            }
            else if (already.includes(value)) {
                if (!window.lmTesting) alert('Relationship with this character already exists');
            } else {
                var name = $(this).find('option:selected').text();
                add_relationship(value, name);
            }

            $(this).val(null).trigger('change');
        });
    });

});

</script>
