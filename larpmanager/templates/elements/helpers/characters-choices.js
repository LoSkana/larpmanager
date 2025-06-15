{% load i18n %}

<script>

window.addEventListener('DOMContentLoaded', function() {

    $(function() {
        $('#id_characters_tr td').append("<br class='show' /><br class='show' /><a id='multichoice_available'>{{ show_available_chars }}</a>");

        $('#multichoice_available').click(function(event) {
            event.preventDefault();

            request = $.ajax({
                url: "{% url 'orga_multichoice_available' event.slug run.number %}",
                method: "POST",
                data: {'eid': '{{ eid }}', 'type': '{{ type }}'},
                datatype: "json",
            });

            request.done(function(data) {
                res = data["res"];
                html = "";
                console.log(res);
                for (let index in res) {
                    console.log(index);
                    console.log(res[index]);
                    html += "{1}<br /><br />".format(res[index][0], res[index][1]);
                }

                uglipop({class:'popup', source:'html', content: html});

            });

            return false;
        });
    });
});

</script>
