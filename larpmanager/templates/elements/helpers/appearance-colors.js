{% load i18n %}

<script>

window.addEventListener('DOMContentLoaded', function() {

    /**
     * Convert hex color to RGB comma-separated string
     * @param {string} hex - Hex color string (e.g., '#FF0000' or 'FF0000')
     * @returns {string} RGB values as comma-separated string (e.g., '255,0,0')
     */
    function hexToRgb(hex) {
        if (!hex) {
            return '';
        }

        // Remove # if present
        const hexWithoutHash = hex.replace(/^#/, '');

        // Validate hex format: exactly 6 hexadecimal characters
        if (!/^[0-9A-Fa-f]{6}$/.test(hexWithoutHash)) {
            return '';
        }

        try {
            const r = parseInt(hexWithoutHash.substring(0, 2), 16);
            const g = parseInt(hexWithoutHash.substring(2, 4), 16);
            const b = parseInt(hexWithoutHash.substring(4, 6), 16);
            return `${r},${g},${b}`;
        } catch (e) {
            return '';
        }
    }

    /**
     * Update CSS custom property for a specific color
     * @param {string} property - CSS custom property name (e.g., '--pri-rgb')
     * @param {string} hexColor - Hex color value
     */
    function updateColorProperty(property, hexColor) {
        const rgbValue = hexToRgb(hexColor);
        if (rgbValue) {
            document.documentElement.style.setProperty(property, rgbValue);
        }
    }

    /**
     * Set up color input listener
     * @param {string} inputId - ID of the color input element
     * @param {string} cssProperty - CSS custom property to update
     */
    function setupColorListener(inputId, cssProperty) {
        const input = document.getElementById(inputId);
        if (input) {
            // Update on input change
            input.addEventListener('input', function() {
                updateColorProperty(cssProperty, this.value);
            });

            // Also update on change (for color picker confirmation)
            input.addEventListener('change', function() {
                updateColorProperty(cssProperty, this.value);
            });
        }
    }

    // Set up listeners for all three color inputs
    setupColorListener('id_pri_rgb', '--pri-rgb');
    setupColorListener('id_sec_rgb', '--sec-rgb');
    setupColorListener('id_ter_rgb', '--ter-rgb');

    /**
     * Show or hide fields that are only relevant for the halo (custom) theme.
     * Each field is wrapped in a <tr id="<field_id>_tr"> by the form template.
     * @param {string} theme - The selected theme value
     */
    function updateThemeFields(theme) {
        var haloOnlyFields = [
            'id_background',
            'id_pri_rgb',
            'id_sec_rgb',
            'id_ter_rgb',
            'id_association_css',
            'id_event_css',
        ];
        var isHalo = (theme === 'halo');
        haloOnlyFields.forEach(function(fieldId) {
            var row = document.getElementById(fieldId + '_tr');
            if (row) {
                row.style.display = isHalo ? '' : 'none';
            }
        });
    }

    var themeSelect = document.getElementById('id_theme');
    if (themeSelect) {
        themeSelect.addEventListener('change', function() {
            updateThemeFields(this.value);
        });
        // Apply immediately on page load
        updateThemeFields(themeSelect.value);
    }

});

</script>
