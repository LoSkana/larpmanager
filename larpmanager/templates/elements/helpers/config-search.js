{% load i18n %}

<script>

window.addEventListener('DOMContentLoaded', function() {

    function search(key) {
        $('tr').each(function( index ) {
            chi = $(this).children();
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
        $('.section-link').each(function( index ) {
            tog = $(this).attr("tog");
            el = $('.' + tog)
            if (el.find('.visib').length == 0)
                el.hide(300);
            else
                el.show(300);

        });
    }

    $(function() {
        var input_search = '<input type="text" name="search" id="search" placeholder="Search" />';
        $('.page_orga_config').prepend(input_search);
        $('.page_exe_config').prepend(input_search);

        $('#search').on('input', function() { search($(this).val()); });
    });

});

</script>
