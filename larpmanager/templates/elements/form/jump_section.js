{% load tz show_tags static  i18n %}

{% if form.jump_section %}

<script>

window.addEventListener('DOMContentLoaded', function() {
    $(document).ready(function(){
        setTimeout(()=> {
            $('a.my_toggle[tog="sec_{{ form.jump_section | slugify }}"]').trigger('click');
        }, 100);
    });
});

</script>


{% endif %}
