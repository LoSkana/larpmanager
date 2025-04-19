<script>

window.addEventListener('DOMContentLoaded', function() {
    $(function() {
        $('#search').on('input', function() { search($(this).val()); });

            setTimeout(function() {
                $('*[data-column="0"]').click();
            }, 200);
        });
});

function search(key) {
    $('.fea').each(function( index ) {
        chi = $(this).children();
        var tx = chi.eq(0).html() + chi.eq(2).html();

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
    $('.show').each(function( index ) {
        mod = $(this).attr("mod");
        // console.log(mod);
        if($(this).find('.visib').length == 0)
            $('.feat_' + mod).hide(300);
        else
            $('.feat_' + mod).show(300);

    });
}

</script>
