{% load i18n %}

<script>

window.addEventListener('DOMContentLoaded', function() {
    $(document).ready(function() {
        setTimeout(function() {
        {% for key, que in form_questions.items %}
            {% if que.typ == 'teaser' or que.typ == 'text' %}
                $('a.my_toggle[tog="q_{{ key }}"]').trigger('click');
            {% endif %}
        {% endfor %}
        }, 100);
    });
});

</script>
