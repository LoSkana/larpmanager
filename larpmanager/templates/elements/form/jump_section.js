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

                $('#page-wrapper').animate({
                    scrollTop: el.offset().top - headerHeight * 2
                }, 0);
            }

        }, 100);
    });
});

</script>


{% endif %}
