<script nonce="{{ csp_nonce }}">
// Open the member profile popup on click of a.post_popup_member
window.addEventListener('DOMContentLoaded', function() {
    $(document).on('click', '.post_popup_member', function () {

        // Show spinner only after 500ms delay
        let spinnerTimeout = setTimeout(function() {
            start_spinner();
        }, 500);

        let request = $.ajax({
            url: "{% url 'orga_registration_member' run.get_slug %}",
            method: "POST",
            data: { mid: $(this).attr("pop") },
            datatype: "json",
        });

        request.done(function(res) {
            // Clear the spinner timeout since request completed
            clearTimeout(spinnerTimeout);

            if (res.k == 0) return;
            stop_spinner();

            window.openLmModal(res.v, 'popup');

            $('#lm-modal').scrollTop( 0 );
            $('#lm-modal .hide').hide();
        });

        return false;
    });
});
</script>
