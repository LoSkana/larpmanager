{% load i18n %}

<script>

window.addEventListener('DOMContentLoaded', function() {

    $(function() {
        $('.feature_checkbox a').click(function(event) {
            event.preventDefault();

            request = $.ajax({
                url: "{% url 'feature_description' %}",
                method: "POST",
                data: {'fid': $(this).attr("feat")},
                datatype: "json",
            });

            request.done(function(data) {
                if (data["res"] != 'ok') return;

                uglipop({class:'popup', source:'html', content: data['txt']});

                setTimeout(() => {
                  const iframe = document.querySelector('.uglipop-content iframe.tutorial');
                  if (iframe) {
                    iframe.onload = () => {
                      const doc = iframe.contentDocument || iframe.contentWindow.document;
                      const style = doc.createElement('style');
                      style.textContent = `
                        #header, header, #tutorials .column, #tutorials .navig { display: none }
                        #main { padding: 0; width: 100%; max-width: 100%; }
                        #page-wrapper { padding: 0; }
                      `;
                      doc.head.appendChild(style);
                    };
                  }
                }, 100);

            });

            return false;
        });
    });
});

</script>
