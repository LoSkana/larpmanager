 window.addEventListener('DOMContentLoaded', function() {
        function toggleOptions() {
            var selectedValue = $('#id_typ').val();

            if (["m", "s"].includes(selectedValue)) {
                $('#options').fadeIn();
            } else {
                $('#options').fadeOut();
            }

            max_lengtheable = ["m", "t", "p", "name", "teaser", "text", "concept", "title",  "keywords", "safety"]
            if (max_lengtheable.includes(selectedValue)) {
                $('#id_max_length_tr').fadeIn();
            } else {
                $('#id_max_length_tr').fadeOut();
            }

            if (["s", "m", "t", "p"].includes(selectedValue)) {
                $('#id_printable_tr').fadeIn();
                $('#id_visibility_tr').fadeIn();
            } else {
                $('#id_printable_tr').fadeOut();
                $('#id_visibility_tr').fadeOut();
            }
        }

        $(document).ready(function() {
            setTimeout(toggleOptions, 10);

            $('#id_typ').on('change', function() {
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
