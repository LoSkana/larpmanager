{{ dependencies|json_script:"option-dependencies" }}
<script>
var all_dependencies = JSON.parse(document.getElementById('option-dependencies').textContent);

// options required by each option, and options required by each question
var dependencies = all_dependencies.options || {};
var question_dependencies = all_dependencies.questions || {};

// safety bound on the passes done to settle chained requirements
var dependencies_max_passes = 20;

function check_dependencies(dependencies) {
    let selects = [];
    let checkboxes = [];
    let radios = [];
    let remainingDependencies = [...dependencies]; // Create a copy of the dependencies array to manipulate it

    // Collect the selects that contain dependency values
    $('select').each(function () {
        const name = $(this).attr('name');
        let values = $(this).val();

        if (values === null || values === undefined) return;

        // multiple selects answer with an array: check every chosen value
        if (!Array.isArray(values)) values = [values];

        values.forEach(function (val) {
            if (remainingDependencies.includes(val)) {
                // Remove the found value from dependencies
                remainingDependencies = remainingDependencies.filter(v => v !== val);
                if (!selects.includes(name)) {
                    selects.push(name);
                }
            }
        });
    });

    // Collect checkbox groups that contain dependency values
    $('input[type="checkbox"]:checked').each(function () {
        const name = $(this).attr('name');
        const value = $(this).val();

        if (value && remainingDependencies.includes(value)) {
            // Remove the found value from dependencies
            remainingDependencies = remainingDependencies.filter(v => v !== value);
            if (!checkboxes.includes(name)) {
                checkboxes.push(name);
            }
        }
    });

    // Collect radio groups that contain dependency values
    $('input[type="radio"]:checked').each(function () {
        const name = $(this).attr('name');
        const value = $(this).val();

        if (value && remainingDependencies.includes(value)) {
            remainingDependencies = remainingDependencies.filter(v => v !== value);
            if (!radios.includes(name)) {
                radios.push(name);
            }
        }
    });

    // Check the remaining values in dependencies
    for (let val of remainingDependencies) {
        // If the remaining value is in a select not yet selected, return false
        let selectFound = $('select').not(function() {
            return selects.includes($(this).attr('name'));
        }).is(function () {
            return $(this).find('option').toArray().some(option => $(option).val() === val);
        });

        if (selectFound) {
            return false; // If the remaining value is in a select, return false
        }

        // If the remaining value is in a checkbox that was not considered before, return false
        let checkboxFound = $('input[type="checkbox"]').is(function () {
            return $(this).val() === val && !checkboxes.includes($(this).attr('name'));
        });

        if (checkboxFound) {
            return false; // If the remaining value is in a checkbox that was not included, return false
        }

        // If the remaining value is in a radio group not yet selected, return false
        let radioFound = $('input[type="radio"]').is(function () {
            return $(this).val() === val && !radios.includes($(this).attr('name'));
        });

        if (radioFound) {
            return false; // If the remaining value is in a radio group, return false
        }
    }

    return true; // If all dependencies are satisfied, return true
}

// Hide or show an element gated by the requirements.
// A class is used instead of an inline style: the collapse toggle of the choice widgets
// ("show / hide other options") manages its own 'hide' class, and an inline display would win
// over it, leaving the collapsed options visible.
function toggle_dependency_element(el, available) {
    el.toggleClass('dep-hidden', !available);
}

function disable_dependencies_pass() {
    reset_select = [];
    let changed = false;

    for (const [key, options] of Object.entries(dependencies)) {
        available = check_dependencies(options);

        // disable selects with that value
        $('select option[value="' + key + '"]').prop('hidden', !available);
        toggle_dependency_element($('#hp_' + key), available);

        if (!available) {
            // check if there are select with disabled selected value
            $('select').each(function() {
                var selectedOption = $(this).find('option:selected');
                if (selectedOption.val() === key) {
                    reset_select.push($(this));
                }
            });
        }

        // disable checkboxes and radios with that value
        $('input[type="checkbox"][value="' + key + '"], input[type="radio"][value="' + key + '"]').each(function() {
            toggle_dependency_element($(this), available);
            toggle_dependency_element($(this).closest('label'), available);
            toggle_dependency_element($(this).closest('div'), available);

            if (!available && $(this).is(':checked')) {
                $(this).prop('checked', false);
                changed = true;
            }
        });
    }

    $(reset_select).each(function() {
      var $select = $(this);

      // look for first option without value
      var $option = $select.find('option').filter(function() {
        var value = $(this).attr('value');
        return typeof value === 'undefined' || value === '';
      }).first();

      // if does not exist, create it
      if ($option.length === 0) {
        $option = $('<option disabled="disabled" value="">-------</option>');
        $select.prepend($option);
      }

      // select it
      $option.prop('selected', true);
      changed = true;
    });

    return changed;
}

function disable_questions_pass() {
    let changed = false;

    for (const [key, options] of Object.entries(question_dependencies)) {
        const el = $('#id_que_' + key);
        if (!el.length) continue;

        const available = check_dependencies(options);
        const hidden = el.closest('tr').hasClass('not-required');

        // hiding a question clears its answers, which can gate the questions requiring them
        if (!available && !hidden) changed = true;

        toggle_question(el, available);
    }

    return changed;
}

function disable_dependencies() {
    // deselecting an option can invalidate the ones requiring it: repeat until nothing else changes
    for (let pass = 0; pass < dependencies_max_passes; pass++) {
        const options_changed = disable_dependencies_pass();
        const questions_changed = disable_questions_pass();
        if (!options_changed && !questions_changed) return;
    }
}

window.addEventListener('DOMContentLoaded', function() {
    $(function () {
        disable_dependencies();

        $('select, input[type="checkbox"], input[type="radio"]').on('change', function() {
            disable_dependencies();
        });
    });
});
</script>
