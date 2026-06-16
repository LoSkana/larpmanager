{% load i18n %}
{% if form.multichoice_configs %}
<script>
window.addEventListener('DOMContentLoaded', function() {
    $(function() {
        {% for cfg in form.multichoice_configs %}
        $('#id_{{ cfg.field_id }}_tr td').append("<span id='{{ cfg.link_id }}_wrap'><br class='show' /><br class='show' /><a id='{{ cfg.link_id }}'>{{ cfg.label }}</a></span>");
        if ($('[tog="f_id_{{ cfg.field_id }}"]').length) {
            $('#{{ cfg.link_id }}_wrap').hide().addClass('f_id_{{ cfg.field_id }}');
        }
        $('#{{ cfg.link_id }}').click(function(event) {
            event.preventDefault();

            {% if cfg.form_orga %}
            {% if form.orga %}
            var orga_{{ cfg.link_id }} = 1;
            {% else %}
            var orga_{{ cfg.link_id }} = 0;
            {% endif %}
            {% endif %}

            {% if cfg.form_edit_uuid %}
            {% if form.instance.pk %}
            var edit_uuid_{{ cfg.link_id }} = '{{ form.instance.uuid }}';
            {% else %}
            var edit_uuid_{{ cfg.link_id }} = "";
            {% endif %}
            {% endif %}

            var postData_{{ cfg.link_id }} = {
                {% for k, v in cfg.data.items %}'{{ k }}': '{{ v }}',{% endfor %}
                {% if cfg.ctx_edit_uuid %}'edit_uuid': '{{ edit_uuid }}',
                {% elif cfg.form_edit_uuid %}'edit_uuid': edit_uuid_{{ cfg.link_id }},{% endif %}
                {% if cfg.form_orga %}'orga': orga_{{ cfg.link_id }},{% endif %}
            };

            request = $.ajax({
                url: '{{ cfg.url }}',
                method: "POST",
                data: postData_{{ cfg.link_id }},
                datatype: "json",
            });

            request.done(function(data) {
                res = data["res"];
                html = "<h2>{{ cfg.label }} - {{ run.event.name }}</h2>";
                for (let index in res) {
                    html += "{1}<br /><br />".format(res[index][0], res[index][1]);
                }
                uglipop({class:'popup_small', source:'html', content: html});
            });

            return false;
        });
        {% endfor %}
    });
});
</script>
{% endif %}
