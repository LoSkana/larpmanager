 window.addEventListener('DOMContentLoaded', function() {
        function toggleOptions() {
            var selectedValue = $('#id_typ').val();

            var speed = 300;

            if (["m", "s"].includes(selectedValue)) {
                if (!$('#options').is(':visible')) {
                    $('#options').fadeIn(speed);
                }
            } else {
                if ($('#options').is(':visible')) {
                    $('#options').fadeOut(speed);
                }
            }

            max_lengtheable = ["m", "t", "p", "e", "name", "teaser", "text", "title"]
            if (max_lengtheable.includes(selectedValue)) {
                $('#id_max_length_tr').fadeIn(speed);
            } else {
                $('#id_max_length_tr').fadeOut(speed);
            }

            if (["s", "m", "t", "p", "e"].includes(selectedValue)) {
                $('#id_printable_tr').fadeIn(speed);
                $('#id_visibility_tr').fadeIn(speed);
            } else {
                $('#id_printable_tr').fadeOut(speed);
                $('#id_visibility_tr').fadeOut(speed);
            }

            if (["name", "teaser", "text", "faction"].includes(selectedValue)) {
                $('#id_visibility_tr').fadeOut(speed);
            } else {
                $('#id_visibility_tr').fadeIn(speed);
            }
        }

        $(document).ready(function() {
            // move options
            $('#options').insertBefore('#form_submit');

            setTimeout(toggleOptions, 10);

            $('#id_typ').on('change', function() {
                toggleOptions();
            });

            $('#id_status').on('change', function() {
                toggleOptions();
            });

            {% if num %}
                $('.new').on('click', function() {
                    window.location.href = newUrl;
                });
            {% else %}
                $('.new').on('click', function() {
                    var $form = $('#main_form');

                    var $hiddenInput = $('<input>')
                        .attr('type', 'hidden')
                        .attr('name', 'new_option')
                        .attr('value', 1);

                    $form.append($hiddenInput);

                    $form.submit();
                });
            {% endif %}
        });
    });
