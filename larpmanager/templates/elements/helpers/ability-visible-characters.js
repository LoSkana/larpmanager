<script nonce="{{ csp_nonce }}">
(function () {
    function updateVisibleCharacters() {
        var visible = $('#id_visible');
        var row = $('#id_visible_characters_tr');
        if (!visible.length || !row.length) return;
        if (visible.is(':checked')) {
            row.hide();
        } else {
            row.show();
        }
    }

    $(document).ready(function () {
        updateVisibleCharacters();
        $('#id_visible').on('change', updateVisibleCharacters);
    });
}());
</script>
