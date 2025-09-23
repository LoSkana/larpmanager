{% include "elements/writing/token.js" %}

<script>

{% if num %}

var eid = {{ num }};
var type = '{{ type }}';

var timeout = 10 * 1000;
var post_url = "{% url 'working_ticket' %}";

function submitForm() {

    $.ajax({
        type: "POST",
        url: post_url,
        data: {eid: eid, type: type, token: token},
        success: function(msg) {
            if (msg.warn) {
                $.toast({
                    text: msg.warn,
                    showHideTransition: 'slide',
                    icon: 'error',
                    position: 'mid-center',
                    textAlign: 'center',
                    allowToastClose: true,
                    hideAfter: false,
                    stack: 1
                });
            }
        }
    });
    setTimeout(()=>submitForm(), timeout);
}

window.addEventListener('DOMContentLoaded', function() {
    $(function() {
        submitForm();
    });
});

{% endif %}

</script>
