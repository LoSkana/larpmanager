{% load i18n %}

<script>

window.addEventListener('DOMContentLoaded', function() {

    function search(key) {
        $('.feature_checkbox').each(function( index ) {
            chi = $(this).children();
            console.log(chi);
            var tx = chi.eq(0).html() + chi.eq(1).html();

            if (tx.toLowerCase().includes(key.toLowerCase())) {
                $(this).show(300);
                $(this).addClass('visib');
            } else {
                $(this).hide(300);
                $(this).removeClass('visib');
            }
        });

        setTimeout(show_mod, 500);
    }

    function show_mod(key) {
        $('tr').each(function( index ) {
            el = $(this);
            if (el.find('.visib').length == 0) {
                el.hide(300);
            } else {
                el.show(300);
            }
        });
    }

    $(function() {
        var input_search = '<input type="text" name="search" id="search" placeholder="Search" /><br />';
        $('.page_exe_features').prepend(input_search);
        $('.page_orga_features').prepend(input_search);

        $('#search').on('input', function() { search($(this).val()); });
    });

});

</script>
