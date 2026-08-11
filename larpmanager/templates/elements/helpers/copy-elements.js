{% load i18n %}

<script>

// handle select all / deselect all of the copy element cards

window.addEventListener('DOMContentLoaded', function() {

    function toggle_section(link, checked) {
        $(link).closest('.copy-pick-section').find('input[type=checkbox]').prop('checked', checked);
    }

    $(document).on('click', '.copy-pick-all', function(e) {
        e.preventDefault();
        toggle_section(this, true);
    });

    $(document).on('click', '.copy-pick-none', function(e) {
        e.preventDefault();
        toggle_section(this, false);
    });

});

</script>
