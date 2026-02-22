{% load i18n %}

<script>

let timeout = null;

let tutorials_url = "{% url 'tutorials' %}";

let guides_url = "{% url 'guides' %}";

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

{% if run %}
    let run_id = '{{ run.uuid }}';
{% else %}
    let run_id = '';
{% endif %}

function search_tutorial() {
    const query = $('#tutorial_query').val().trim();
    if (query === '') return;

    request = $.ajax({
        url: "{% url 'tutorial_query' %}",
        method: "POST",
        data: {'q': query, 'r': run_id},
        datatype: "json",
    });

    request.done(function(data) {
        // links text
        link_text = '';
        data.links.forEach(item => {
            link_text += '<tr><td><h3>' + item.name + '</h3></td><td>' +
            '<td><p><a href="' + item.href + '" target="_blank"><i>' + item.descr + ' </i></a></p></td></tr>';
        });

        if (link_text.trim() !== "") {
            link_text = '<h2>Links</h2><table >' + link_text + '</table>';
        }

        // guides text
        guide_text = '';
        data.guides.forEach(item => {
            guide_text += '<tr><td><h3>' + item.title + '</h3></td><td>' +
            '<td><p><a href="' + guides_url + item.slug + '" target="_blank"><i>' + item.snippet + ' [...]</i></a></p></td></tr>';
        });

        if (guide_text.trim() !== "") {
            guide_text = '<h2>Guides</h2><table >' + guide_text + '</table>';
        }

        // tutorials text
        tutorial_text = '';
        data.tutorials.forEach(item => {
            tutorial_text += '<tr><td><h3>' + item.title + ' - ' + item.section + '</h3></td><td>' +
            '<td><p><a href="' + tutorials_url + item.slug + '#' + slugify(item.section) + '" target="_blank"><i>' + item.snippet + ' [...]</i></a></p></td></tr>';
        });

        if (tutorial_text.trim() !== "") {
            tutorial_text = '<h2>Tutorials</h2><table >' + tutorial_text + '</table>';
        }

        // prepare results
        result = link_text + guide_text + tutorial_text

        if (result.trim() === "")
            result = "{% trans "No results found; please try with more simpler terms (remember to write in English)" %}";

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
