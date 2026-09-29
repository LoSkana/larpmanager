{% load show_tags i18n %}

<script>

// handle bulk operations

window.addEventListener('DOMContentLoaded', function() {
    $(document).on("lm_ready", function() {

        // Set to select rows when bulk is available
        Object.keys(window.datatables).forEach(function(key) {
            var table = window.datatables[key];
            table.on('click', 'tbody tr', function (e) {
                if ($("#main_bulk").is(":visible")) {
                    e.currentTarget.classList.toggle('selected');
                }
            });
        });

        // Show list of target when operation is selected
        $("#main_bulk #operation").on("change", function() {
            $(".objs").addClass('hide');
            var val = $(this).val();
            $("#objs_" + val).removeClass('hide');
        }).trigger("change");

$("#main_bulk #exec").on("click", function(e) {
  e.preventDefault();

  var payload = get_bulk_payload();
  if (!payload.uuids.length) {
    $.toast({
      text: "{% filter escapejs %}{% trans "Select at least one row first" %}{% endfilter %}",
      showHideTransition: 'slide',
      icon: 'warning',
      position: 'top-center',
      textAlign: 'center',
    });
    return;
  }

  window.lmConfirm("{% filter escapejs %}{% trans "Apply this operation to the selected elements?" %}{% endfilter %}", function() {
    run_bulk(payload);
  });
});

// Collect the chosen operation, its target and the selected table rows.
function get_bulk_payload() {

  // get operation
  var operation = $("#main_bulk #operation").val();

  // get non hidden target choice
  var $activeObjs = $("#main_bulk .objs").not(".hide").first();
  var target = $activeObjs.find("option:selected").first().val();

  // get ids from selected table rows
  var uuids = [];
  Object.keys(window.datatables).forEach(function(key) {
    var table = window.datatables[key];
    table.rows('.selected').every(function() {
      var uuid = this.node().id;
      if (uuid) uuids.push(uuid);
    });
  });

  return {
    operation: operation,
    target: target,
    uuids: uuids
  };
}

function run_bulk(payload) {

  $.ajax({
    url: "{{ request.path }}",
    method: "POST",
    data: payload,
    success: function(resp) {
        if (resp.error) {
            $.toast({
                text: resp.error,
                showHideTransition: 'slide',
                icon: 'error',
                position: 'mid-center',
                textAlign: 'center',
            });
        }
        window.location.reload();
    },
    error: function(xhr) {
      console.error("Error", xhr.status, xhr.responseText);
    }
  });
}


    });
});
</script>
