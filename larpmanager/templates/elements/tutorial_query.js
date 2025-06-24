{% load i18n %}

<script>

let timeout = null;

let tutorials_url = "{% url 'tutorials' %}";

function slugify(text) {
    return text
        .toString()
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .toLowerCase()
        .trim()
        .replace(/\s+/g, '-')
        .replace(/[^\w\-]+/g, '')
        .replace(/\-\-+/g, '-')
        .replace(/^-+/, '')
        .replace(/-+$/, '');
}


window.addEventListener('DOMContentLoaded', function() {
    $(function() {

        $('#tutorial_query').on('input', function () {
            clearTimeout(timeout);
            timeout = setTimeout(function () {
                const query = $('#tutorial_query').val().trim();
                if (query === '') return;

                request = $.ajax({
                    url: "{% url 'tutorial_query' %}",
                    method: "POST",
                    data: {'q': query},
                    datatype: "json",
                });

                request.done(function(data) {
                    result = '';
                    data.forEach(item => {
                        result += '<h2><a href="' + tutorials_url + item.slug + '#' + slugify(item.section) + '" target="_blank">'
                            + item.title + ' - ' + item.section + '</a></h2><p><i>' + item.snippet + '</i></p>';
                    });

                    if (result.trim() === "") return;

                    uglipop({class:'popup_query', source:'html', content: result});
                });

            }, 1000);
        });

    });
});

</script>
