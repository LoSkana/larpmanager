{% load i18n %}

<script>

window.addEventListener('DOMContentLoaded', function() {

    $(function() {
        $('#id_characters_new_tr td').append("<br class='show' /><br class='show' /><a id='multichoice_available'>{{ show_available_chars }}</a>");

        $('#multichoice_available').click(function(event) {
            event.preventDefault();

            request = $.ajax({
                url: "{% url 'orga_multichoice_available' event.slug run.number %}",
                method: "POST",
                data: {'type': 'registrations'},
                datatype: "json",
            });

            request.done(function(data) {
                res = data["res"];
//                html = "<a id='multichoice_add'>{% trans 'Add' %}</a> <br /><br />";
                html = "";
                console.log(res);
                for (let index in res) {
                    console.log(index);
                    console.log(res[index]);
                    //html += "<input class='checkbox' type='checkbox' value='{0}'><span>{1}</span><br /><br />".format(res[index][0], res[index][1]);
                    html += "{1}<br /><br />".format(res[index][0], res[index][1]);
                }

                uglipop({class:'popup', source:'html', content: html});

//                $('#multichoice_add').click(function(event) {
//                    event.preventDefault();
//                    values = [];
//                    $('#uglipop_popbox .checkbox:checked').each(function() {
//                        let checkboxValue = $(this).val();
//                        values.push($(this).next('span').text());
//                    });
//
//                    $('.select2-search__field').val(values[0]);
//
//                });
            });

            return false;
        });
    });
});

</script>
