{% load i18n %}

<script>

window.addEventListener('DOMContentLoaded', function() {

    $(function() {

        $('#id_factions_list_tr td').append("<br class='show' /><br class='show' /><a id='factions_available'>{{ form.show_available_factions }}</a>");

        $('#factions_available').click(function(event) {
            event.preventDefault();

            {% if form.orga %}
            var orga = 1;
            {% else %}
            var orga = 0;
            {% endif %}

            {% if form.instance.pk %}
            var eid = {{ form.instance.pk }};
            {% else %}
            var eid = 0;
            {% endif %}

            request = $.ajax({
                url: "{% url 'orga_factions_available' event.slug run.number %}",
                method: "POST",
                data: {'eid': eid, 'orga': orga},
                datatype: "json",
            });

            request.done(function(data) {
                res = data["res"];
                html = "";
                for (let index in res) {
                    html += "{1}<br /><br />".format(res[index][0], res[index][1]);
                }

                uglipop({class:'popup', source:'html', content: html});

            });

            return false;
        });
    });
});

</script>
