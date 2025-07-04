{% load show_tags i18n %}

<script>

const abilities = {{ available | safe }};

window.addEventListener('DOMContentLoaded', function() {
    $(function() {
        $('form').on('submit', function() {
            return confirm('{% trans "Are you sure" %}?');
        });

        $('input[type="submit"]').prop('disabled', true);

        $('#ability_type').on('change', function () {
            const typeId = $(this).val();
            const $abilitySelect = $('#ability_select');
            $abilitySelect.empty().append('<option value="" disabled selected>--- {% trans "Seleziona abilità" %}</option>');
            if (abilities[typeId] && abilities[typeId]['list']) {
                $.each(abilities[typeId]['list'], function (id, label) {
                    $abilitySelect.append($('<option>', { value: id, text: label }));
                });
            }
        });

        $('#ability_select').on('change', function () {
            $('input[type="submit"]').prop('disabled', false);
        });

        const $typeSelect = $('#ability_type');
        if ($typeSelect.children('option').length > 0) {
            $typeSelect.prop('selectedIndex', 0).trigger('change');
        }
    });
});

</script>
