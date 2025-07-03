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

function search_tutorial() {
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
            result += '<tr><td><h3>' + item.title + ' - ' + item.section + '</h3></td><td>' +
            '<td><p><a href="' + tutorials_url + item.slug + '#' + slugify(item.section) + '" target="_blank"><i>' + item.snippet + ' [...]</i></a></p></td></tr>';
        });

        if (result.trim() === "")
            result = "{% trans "No results found; please try with more simpler terms (remember to write in English)" %}";
        else result = '<h2>{% trans "Results" %}</h2><table class="no_csv">' + result + '</table>';

        uglipop({class:'popup_query', source:'html', content: result});
    });

}


window.addEventListener('DOMContentLoaded', function() {
    $(function() {

        $('#tutorial_query').on('input', function () {
            clearTimeout(timeout);
            timeout = setTimeout(search_tutorial, 1000);
        });

        $('#tutorial_query_go').on('click', function () {
            clearTimeout(timeout);
            search_tutorial();
        });

    });
});

</script>
