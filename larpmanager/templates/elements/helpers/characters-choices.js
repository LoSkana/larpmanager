{% load i18n %}

<script>

window.addEventListener('DOMContentLoaded', function() {

    $(function() {
        $('#id_characters_tr td').append("<br class='show' /><br class='show' /><a id='multichoice_available'>{{ show_available_chars }}</a>");

        $('#multichoice_available').click(function(event) {
            event.preventDefault();

            request = $.ajax({
                url: "{% url 'orga_multichoice_available' run.get_slug %}",
                method: "POST",
                data: {'edit_uuid': '{{ edit_uuid }}', 'type': '{{ type }}'},
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
