{% include "elements/writing/token.js" %}

<script>

{% if num %}

var w_eid = {{ num }};
var w_type = '{{ type }}';

var w_timeout = 1 * 1000;
var working_ticket_url = "{% url 'working_ticket' %}";

function callWorkingTicket() {

    $.ajax({
        type: "POST",
        url: working_ticket_url,
        data: {eid: w_eid, type: w_type, token: token},
        success: function(msg) {
            if (msg.warn) {
                $.toast({
                    text: msg.warn,
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
    setTimeout(()=>callWorkingTicket(), w_timeout);
}

window.addEventListener('DOMContentLoaded', function() {
    $(function() {
        callWorkingTicket();
    });
});

{% endif %}

</script>
