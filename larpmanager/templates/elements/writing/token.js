<script>

if (typeof window.generateToken === 'undefined') {
    window.generateToken = function(length = 32) {
        const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
        let result = '';
        for (let i = 0; i < length; i++) {
            result += chars.charAt(Math.floor(Math.random() * chars.length));
        }
        return result;
    };

    const tokenKey = 'sessionToken';

    window.token = sessionStorage.getItem(tokenKey);

    if (!window.token) {
        window.token = generateToken();
        sessionStorage.setItem(tokenKey, window.token);
    }
}

</script>
