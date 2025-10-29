<script>
window.addEventListener('DOMContentLoaded', function() {

    $(function() {
        $('#slug').on('slug:changed', function (e, cleanedVal) {
            $('.slug_pre').text("Preview: https://" + cleanedVal + base_domain);
        });
    });
});
</script>
