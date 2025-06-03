{% load i18n %}

{{ TINYMCE_DEFAULT_CONFIG|json_script:"tinymce-config" }}

<script>

const tinymceConfig = JSON.parse(document.getElementById('tinymce-config').textContent);

window.addEventListener('DOMContentLoaded', function() {

    function addTinyMCETextarea(sel) {
        let config = Object.assign({}, tinymceConfig);
        config.selector = sel + ':not(.tinymce-initialized)';
        config.setup = function (editor) {
            editor.on('init', function () {
                editor.getElement().classList.add('tinymce-initialized');
            });
        };
        tinymce.init(config);
    }

    $(function() {
        {% for key, item in relationships.items %}
            addTinyMCETextarea('.f_{{ key }}_direct textarea');
            addTinyMCETextarea('.f_{{ key }}_inverse textarea');
        {% endfor %}

        document.getElementById('main_form').addEventListener('submit', function(e) {
            tinymce.triggerSave();
        });
    });

});

</script>
