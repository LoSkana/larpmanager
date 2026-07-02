<script>
$(document).ready(function() {
    function sendHeight() {
        if (window.parent && window.parent !== window) {
            const form = document.querySelector('#wrapper form') || document.querySelector('form');
            const height = form ? form.scrollHeight : document.body.scrollHeight;
            window.parent.postMessage({
                type: 'iframe_resize',
                height: height + 50
            }, '*');
        }
    }
    window.lmResizeIframe = sendHeight;
    sendHeight();

    if (window.ResizeObserver) {
        new ResizeObserver(sendHeight).observe(document.querySelector('#wrapper form') || document.querySelector('form') || document.body);
    } else {
        setTimeout(sendHeight, 100);
        setTimeout(sendHeight, 500);
        setTimeout(sendHeight, 1000);
    }

    if (window.tinymce) {
        tinymce.on('AddEditor', function(e) {
            e.editor.on('init', sendHeight);
        });
    }
});
</script>
