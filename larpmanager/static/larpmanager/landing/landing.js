window.addEventListener('DOMContentLoaded', function () {

    // Animated counters for hero stats
    var counters = document.querySelectorAll('.key-number-value');
    var speed = 60;

    counters.forEach(function (counter) {
        counter.innerText = '0';
        var updateCount = function () {
            var target = +counter.getAttribute('data-target');
            var count = +counter.innerText.replace('+', '');
            var increment = target / speed;

            if (count < target) {
                counter.innerText = Math.ceil(count + increment);
                setTimeout(updateCount, 10);
            } else {
                counter.innerText = target;
            }

            counter.innerText += '+';
        };
        updateCount();
    });

    // Scroll-snap strip navigation
    document.querySelectorAll('.strip-nav button[data-strip]').forEach(function (button) {
        button.addEventListener('click', function () {
            var strip = document.getElementById(button.dataset.strip);
            if (!strip || !strip.firstElementChild) {
                return;
            }
            var stepWidth = strip.firstElementChild.offsetWidth + 20;
            var behavior = window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth';
            strip.scrollBy({ left: button.dataset.dir * stepWidth, behavior: behavior });
        });
    });

    // Who-is-this-for tabs: switch the visible description per game style
    document.querySelectorAll('.whofor-tabs button[data-whofor]').forEach(function (tab) {
        tab.addEventListener('click', function () {
            document.querySelectorAll('.whofor-tabs button[data-whofor]').forEach(function (other) {
                other.setAttribute('aria-pressed', other === tab ? 'true' : 'false');
            });
            document.querySelectorAll('.whofor-desc').forEach(function (desc) {
                desc.classList.toggle('active', desc.dataset.whofor === tab.dataset.whofor);
            });
        });
    });

    // Toggle helpers: a.my_toggle shows/hides elements carrying the class in its tog attribute
    document.querySelectorAll('a.my_toggle').forEach(function (toggle) {
        toggle.addEventListener('click', function (event) {
            event.preventDefault();
            var target = toggle.getAttribute('tog');
            if (!target) {
                return;
            }
            document.querySelectorAll('.' + target).forEach(function (element) {
                element.classList.toggle('hide');
            });
        });
    });

    // Slug field with live domain preview
    var refreshSlugPreview = createSlugField('#id_name', function (slug) {
        document.querySelectorAll('.slug_pre').forEach(function (preview) {
            preview.textContent = slug ? 'Preview: https://' + slug + (window.base_domain || '') : 'Preview:';
        });
    });
    var nameInput = document.getElementById('id_name');

    if (refreshSlugPreview && nameInput) {
        refreshSlugPreview();

        // Block organization names without letters or numbers, and repeated submits
        var associationForm = nameInput.closest('form');
        if (associationForm) {
            var submitButton = associationForm.querySelector('[type="submit"]');
            var resubmitDelay = 15000;
            var enableSubmit = function () {
                submitButton.disabled = false;
            };

            associationForm.addEventListener('submit', function (event) {
                if (!/[\p{L}\p{N}]/u.test(nameInput.value)) {
                    event.preventDefault();
                    nameInput.setCustomValidity(nameInput.dataset.invalidMessage);
                    nameInput.reportValidity();
                } else {
                    nameInput.setCustomValidity('');
                    submitButton.disabled = true;
                    // An interrupted submit never navigates away, so it cannot block the form forever
                    setTimeout(enableSubmit, resubmitDelay);
                }
            });
            nameInput.addEventListener('input', function () {
                nameInput.setCustomValidity('');
            });
            // A page restored from the back/forward cache can be submitted again
            window.addEventListener('pageshow', enableSubmit);
        }
    }

    // Demo launch: confirm in a modal first (cloning takes a few seconds), then submit.
    var demoForms = document.querySelectorAll('.get-started-demo-form');
    var demoModal = document.getElementById('demo-confirm-modal');
    var demoConfirmStep = document.getElementById('demo-confirm-step');
    var demoBuildingStep = document.getElementById('demo-building-step');
    var demoProceedButton = document.getElementById('demo-confirm-proceed');
    var demoCloseButton = document.getElementById('demo-confirm-close');
    var pendingDemoForm = null;

    if (demoModal && demoConfirmStep && demoBuildingStep && demoProceedButton) {
        demoForms.forEach(function (form) {
            var card = form.querySelector('.get-started-card');
            if (!card) {
                return;
            }
            card.addEventListener('click', function () {
                pendingDemoForm = form;
                demoConfirmStep.classList.remove('hide');
                demoBuildingStep.classList.add('hide');
                demoModal.showModal();
            });
        });

        demoProceedButton.addEventListener('click', function () {
            if (!pendingDemoForm) {
                return;
            }
            demoConfirmStep.classList.add('hide');
            demoBuildingStep.classList.remove('hide');
            pendingDemoForm.requestSubmit();
        });

        if (demoCloseButton) {
            demoCloseButton.addEventListener('click', function () {
                demoModal.close();
            });
        }

        // Close when clicking the backdrop (outside the dialog bounds)
        demoModal.addEventListener('click', function (event) {
            var rect = demoModal.getBoundingClientRect();
            if (event.clientX < rect.left || event.clientX > rect.right ||
                event.clientY < rect.top || event.clientY > rect.bottom) {
                demoModal.close();
            }
        });
    }

    // Coming back with the browser back button may restore the frozen page from
    // the bfcache: close any stuck modal so the user can start another demo
    window.addEventListener('pageshow', function (event) {
        if (!event.persisted) {
            return;
        }
        pendingDemoForm = null;
        if (demoModal && demoModal.open) {
            demoModal.close();
        }
    });

    window._lmReady = true;

});
