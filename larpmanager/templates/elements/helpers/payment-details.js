{% load i18n %}

<script>

const methodsMapping = {
    {% for obj in form.methods %}
        {{ obj.id }}: "{{ obj.name | slugify }}"{% if not forloop.last %},{% endif %}
    {% endfor %}
};

window.addEventListener('DOMContentLoaded', function() {

    $(function() {

        const checkboxes = document.querySelectorAll('#id_payment_methods input[type="checkbox"]');

        checkboxes.forEach(cb => {
            const slug = methodsMapping[parseInt(cb.value)];
            var link = $('a[tog="sec_' + slug + '"]');
            if (!cb.checked) {
                link.hide();
            } else {
                setTimeout(() => link.click(), 100);
            }

            cb.addEventListener('click', function () {
                var sec_visible = $('.sec_' + slug).is(':visible');
                link.fadeToggle(200);
                if (sec_visible != this.checked) link.click();
            });
        });
    });

});

</script>
