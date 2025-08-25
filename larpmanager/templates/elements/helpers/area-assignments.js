{% load i18n %}

<script>

window.addEventListener('DOMContentLoaded', function() {

    $(document).on("lm_ready", function() {

        // update data-order of assignments to allow table to sort them
        const table = $('#inv_assignments').DataTable();

        $(document).on('change', 'td.inp-sel input[type=checkbox]', function () {
          const td = $(this).closest('td.inp-sel');
          td.attr('data-order', this.checked ? '1' : '0');
          console.log(td.attr('data-order'));

          table.row(td.closest('tr')).invalidate('dom').draw(false);
        });

        $(document).on('input change', 'td.inp-quantity input[type=number]', function () {
          const table = $('#inv_assignments').DataTable();
          const td = $(this).closest('td.inp-quantity');
          const val = parseInt(this.value, 10) || 0;

          td.attr('data-order', val);
          table.row(td.closest('tr')).invalidate('dom').draw(false);
        });

    });
});

</script>
