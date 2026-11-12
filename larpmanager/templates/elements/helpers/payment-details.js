{% load i18n %}

<script nonce="{{ csp_nonce }}">

window.disable_jump = true;

const methodsMapping = {
    {% for obj in form.methods %}
        "{{ obj.uuid }}": "{{ obj.name | slugify }}"{% if not forloop.last %},{% endif %}
    {% endfor %}
};

const wireMethodUuid = "{% for obj in form.methods %}{% if obj.slug == 'wire' %}{{ obj.uuid }}{% endif %}{% endfor %}";

const wireDemoValues = {
    "wire_descr": "{% trans "Wire transfer" as wire_descr %}{{ wire_descr|escapejs }}",
    "wire_payee": "{{ form.instance.name|escapejs }}",
    "wire_iban": "FILL_ME_REAL_IBAN",
};

function prefillWireDemo() {
    const inputs = Object.keys(wireDemoValues).map(key => document.getElementById('id_' + key));
    if (inputs.some(input => !input || input.value.trim() !== '')) return;
    inputs.forEach(input => {
        input.value = wireDemoValues[input.id.replace('id_', '')];
    });
}

window.addEventListener('DOMContentLoaded', function() {

    $(function() {

        const checkboxes = document.querySelectorAll('#id_payment_methods input[type="checkbox"]');

        if (![...checkboxes].some(cb => cb.checked)) {
            const wireCheckbox = [...checkboxes].find(cb => cb.value === wireMethodUuid);
            if (wireCheckbox) wireCheckbox.checked = true;
        }

        checkboxes.forEach(cb => {
            const slug = methodsMapping[cb.value];
            const isWire = wireMethodUuid === cb.value;
            if (isWire && cb.checked) prefillWireDemo();
            var link = $('a[tog="sec_' + slug + '"]');
            if (!cb.checked) {
                link.hide();
            } else {
                setTimeout(() => link.click(), 100);
            }

            cb.addEventListener('click', function () {
                if (isWire && this.checked) prefillWireDemo();
                var sec_visible = $('.sec_' + slug).is(':visible');
                link.fadeToggle(200);
                if (sec_visible != this.checked) link.click();

                $('.sec_' + slug + " input").each(function() {
                  $(this).prop("required", !$(this).prop("required"));
                });
            });


        });

        setTimeout(() => {
            window.disable_jump = false;
        }, 500);
    });

});

</script>
