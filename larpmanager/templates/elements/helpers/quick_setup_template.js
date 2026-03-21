{% load i18n %}

<script>
window.addEventListener('DOMContentLoaded', function() {

    var templateDescriptions = {
        {% for slug, label, icon, desc, feats, configs in form.template_data %}
        "{{ slug }}": {
            label: "{{ label|escapejs }}",
            icon: "{{ icon|escapejs }}",
            description: "{{ desc|escapejs }}"
        }{% if not forloop.last %},{% endif %}
        {% endfor %}
    };

    function buildDescriptionBox(slug) {
        if (!templateDescriptions[slug]) return null;
        var t = templateDescriptions[slug];
        var box = $('<div class="template-description-box"></div>');
        box.html(
            '<p><i class="' + t.icon + '"></i> <strong>' + t.label + '</strong></p>' +
            '<p class="helptext">' + t.description + '</p>'
        );
        return box;
    }

    function updateTemplateUI(selectedValue) {
        // Show or hide manual-section rows
        if (selectedValue === 'manual') {
            $('tr.manual-section').show();
        } else {
            $('tr.manual-section').hide();
        }

        // Update description box below the template selector
        $('#template-desc-box').remove();
        var box = buildDescriptionBox(selectedValue);
        if (box) {
            box.attr('id', 'template-desc-box');
            $('#id_template').closest('tr').after(
                $('<tr><td></td><td></td></tr>').find('td').eq(1).append(box).end()
            );
        }
    }

    $(function() {
        var $select = $('#id_template');
        if (!$select.length) return;

        // Apply on load
        updateTemplateUI($select.val());

        // Apply on change
        $select.on('change', function() {
            updateTemplateUI($(this).val());
        });
    });

});
</script>
