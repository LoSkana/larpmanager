/* Admin changelist autocomplete filter: reload the list when a value is picked or cleared */
django.jQuery(function ($) {
    'use strict';

    $('#changelist-filter select.admin-autocomplete').on('change', function () {
        var params = new URLSearchParams(window.location.search);
        params.delete('p');
        if (this.value) {
            params.set(this.name, this.value);
        } else {
            params.delete(this.name);
        }
        window.location.search = params.toString();
    });
});
