<SCRIPT TYPE="text/javascript">

  emailE = 'larpmanager.com';

  emailE = ('info' + '@' + emailE);

    var ele = document.getElementsByClassName('contact-mail');
    for (var i = 0; i < ele.length; ++i) {
        var item = ele[i];
        item.innerHTML = '<A href="mailto:' + emailE + '">Contact us!</a>';
    }

window.onload = function() {
    setTimeout(loaded, 2000);
}

function loaded() {
    document.body.className += " loaded";
}

</script>



<NOSCRIPT>

  Email address protected by JavaScript

</NOSCRIPT>
