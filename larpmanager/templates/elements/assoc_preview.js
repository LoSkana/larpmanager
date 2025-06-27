<script>
window.addEventListener('DOMContentLoaded', function() {

    $(function() {

        $('#slug').on('input', function() {
            let sl = $(this).val();
            $('.slug_pre').text("Preview: https://" + sl + base_domain);
        });
    });
});
</script>
