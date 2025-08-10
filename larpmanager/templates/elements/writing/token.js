<script>

function generateToken(length = 32) {
    const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
    let result = '';
    for (let i = 0; i < length; i++) {
        result += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    return result;
}

const tokenKey = 'sessionToken';

let token = sessionStorage.getItem(tokenKey);

if (!token) {
    token = generateToken();
    sessionStorage.setItem(tokenKey, token);
}

</script>
