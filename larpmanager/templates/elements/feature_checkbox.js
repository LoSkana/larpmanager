{% load i18n %}

<script>

window.addEventListener('DOMContentLoaded', function() {

    $(function() {
        $('.feature_checkbox a').click(function(event) {
            event.preventDefault();

            request = $.ajax({
                url: "{% url 'feature_description' %}",
                method: "POST",
                data: {'fid': $(this).attr("feat")},
                datatype: "json",
            });

            request.done(function(data) {
                if (data["res"] != 'ok') return;

                uglipop({class:'popup', source:'html', content: data['txt']});

            });

            return false;
        });
    });
});

</script>
