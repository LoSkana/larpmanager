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

    // Slug field: clean input, live domain preview (vanilla port of lm.js slug logic)
    var slugInput = document.getElementById('slug');
    if (slugInput) {
        var slugWarTimeout = null;

        var updateSlugPreview = function (value) {
            document.querySelectorAll('.slug_pre').forEach(function (preview) {
                preview.textContent = 'Preview: https://' + value + (window.base_domain || '');
            });
        };

        var cleanSlug = function (value) {
            return value
                .normalize('NFKD')
                .replace(/[\u0300-\u036f]/g, '')
                .toLowerCase()
                .replace(/[^a-z0-9]/g, '');
        };

        slugInput.addEventListener('input', function () {
            slugInput.dataset.touched = '1';
            var cleaned = cleanSlug(slugInput.value);
            if (cleaned !== slugInput.value) {
                slugInput.value = cleaned;
                document.querySelectorAll('.slug_war').forEach(function (warning) {
                    warning.classList.remove('hide');
                });
                clearTimeout(slugWarTimeout);
                slugWarTimeout = setTimeout(function () {
                    document.querySelectorAll('.slug_war').forEach(function (warning) {
                        warning.classList.add('hide');
                    });
                }, 3000);
            }
            updateSlugPreview(cleaned);
        });

        var nameInput = document.getElementById('id_name');
        if (nameInput) {
            nameInput.addEventListener('input', function () {
                if (!slugInput.dataset.touched) {
                    var autoSlug = cleanSlug(nameInput.value);
                    slugInput.value = autoSlug;
                    updateSlugPreview(autoSlug);
                }
            });
        }
    }

    window._lmReady = true;

});
