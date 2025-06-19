{% load tz show_tags static  i18n %}

{% if jump_section %}

<script>

window.addEventListener('DOMContentLoaded', function() {
    $(document).ready(function(){
        setTimeout(()=> {
            $('a.my_toggle[tog="{{ jump_section }}"]').trigger('click');
        }, 100);
    });
});

</script>


{% endif %}
