{% load tz show_tags static  i18n %}

{% if form.jump_section %}

<script>

window.addEventListener('DOMContentLoaded', function() {
    $(document).ready(function(){
        setTimeout(()=> {
            var el = $('a.my_toggle[tog="sec_{{ form.jump_section | slugify }}"]')

            if (el.length) {
                el.trigger('click');

                var headerHeight = $('header').outerHeight();

            {% if interface_old %}
                $('html, body').animate({
                    scrollTop: el.offset().top - headerHeight
                }, 0);
            {% else %}
                $('#page-wrapper').animate({
                    scrollTop: el.offset().top - headerHeight * 2
                }, 0);
            {% endif %}
            }

        }, 100);
    });
});

</script>


{% endif %}
