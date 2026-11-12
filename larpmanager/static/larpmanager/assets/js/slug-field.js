// Slug field behaviour, shared by the app and the landing pages.

// Sets up the slug input: it stays disabled, so the server generates the slug, until the user asks
// to change it, and it follows the name until the user types a value of their own.
// onPreview receives the slug to show. Returns a function refreshing the slug and its preview, null without a slug field.
function createSlugField(nameSelector, onPreview) {
    const slugInput = document.getElementById('slug');
    if (!slugInput) {
        return null;
    }

    const nameInput = document.querySelector(nameSelector);
    // Filled when the value is generated rather than chosen by the user, and kept across form submits
    const autoInput = document.querySelector('.slug_auto');
    const warnings = document.querySelectorAll('.slug_war');
    const changeLink = document.querySelector('.slug_change');
    let warningTimeout;

    function cleanSlug(value) {
        return value
            .normalize('NFKD')
            .replace(/[\u0300-\u036f]/g, '')
            .toLowerCase()
            .replace(/[^a-z0-9]/g, '');
    }

    function slugFromName() {
        return nameInput ? cleanSlug(nameInput.value).slice(0, slugInput.maxLength) : '';
    }

    function fillFromName() {
        const autoSlug = slugFromName();
        slugInput.value = autoSlug;
        onPreview(autoSlug);
    }

    function showWarning() {
        warnings.forEach(function (warning) {
            warning.classList.remove('hide');
        });
        clearTimeout(warningTimeout);
        warningTimeout = setTimeout(function () {
            warnings.forEach(function (warning) {
                warning.classList.add('hide');
            });
        }, 3000);
    }

    if (changeLink) {
        changeLink.addEventListener('click', function (event) {
            event.preventDefault();
            document.querySelector('.slug_edit').classList.remove('hide');
            changeLink.classList.add('hide');
            slugInput.disabled = false;
            slugInput.focus();
        });
    }

    slugInput.addEventListener('input', function () {
        const cleaned = cleanSlug(slugInput.value);
        if (cleaned !== slugInput.value) {
            slugInput.value = cleaned;
            showWarning();
        }

        // An emptied input means the server generates the slug from the name
        autoInput.value = cleaned ? '' : '1';
        onPreview(cleaned || slugFromName());
    });

    if (nameInput) {
        nameInput.addEventListener('input', function () {
            if (autoInput.value) {
                fillFromName();
            }
        });
    }

    // Restores the preview when the form is shown again after a validation error
    return function () {
        if (slugInput.value && !slugInput.disabled) {
            onPreview(slugInput.value);
        } else {
            fillFromName();
        }
    };
}
