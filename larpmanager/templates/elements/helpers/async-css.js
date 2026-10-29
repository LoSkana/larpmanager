<script nonce="{{ csp_nonce }}">
// Apply preloaded stylesheets once fetched, with a fallback in case the load event already fired
(function() {
    function applyAsyncCss(link) {
        link.rel = 'stylesheet';
        link.removeAttribute('data-async-css');
    }
    document.querySelectorAll('link[data-async-css]').forEach(function(link) {
        link.addEventListener('load', function() { applyAsyncCss(link); });
    });
    window.addEventListener('load', function() {
        document.querySelectorAll('link[data-async-css]').forEach(applyAsyncCss);
    });
})();
</script>
