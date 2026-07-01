$(".hide:visible").hide();

window.addEventListener('DOMContentLoaded', function() {

$.ajaxSetup({
     beforeSend: function(xhr, settings) {
         function getCookie(name) {
             var cookieValue = null;
             if (document.cookie && document.cookie != '') {
                 var cookies = document.cookie.split(';');
                 for (var i = 0; i < cookies.length; i++) {
                     var cookie = jQuery.trim(cookies[i]);
                     // Does this cookie string begin with the name we want?
                     if (cookie.substring(0, name.length + 1) == (name + '=')) {
                         cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                         break;
                     }
                 }
             }
             return cookieValue;
         }
         if (!(/^http:.*/.test(settings.url) || /^https:.*/.test(settings.url))) {
             // Only send the token to relative URLs i.e. locally.
             xhr.setRequestHeader("X-CSRFToken", getCookie('csrftoken'));
         }
     }
});

// Smooth-scroll the page wrapper so the target element sits below the header.
window.jump_to = function(target) {

    var headerHeight = $('header').length
      ? $('header').outerHeight()
      : $('#nav').outerHeight();

    $('#page-wrapper').animate({
        scrollTop: $('#page-wrapper').scrollTop() + $(target).offset().top - headerHeight * 4
    }, 0);
}

// ========== Dialog Modal System ==========

// Show the shared <dialog id="lm-modal"> with given HTML content and CSS class.
window.openLmModal = function(content, cssClass) {
    const dialog = document.getElementById('lm-modal');
    dialog.className = cssClass || 'popup';
    document.getElementById('lm-modal-content').innerHTML = content;
    dialog.showModal();
};

// Close the shared modal dialog if open.
window.closeLmModal = function() {
    const dialog = document.getElementById('lm-modal');
    if (dialog && dialog.open) dialog.close();
};

// Close the modal when clicking the backdrop (outside the dialog bounds).
(function() {
    const dialog = document.getElementById('lm-modal');
    if (!dialog) return;
    dialog.addEventListener('click', function(e) {
        const rect = dialog.getBoundingClientRect();
        if (e.clientX < rect.left || e.clientX > rect.right ||
            e.clientY < rect.top || e.clientY > rect.bottom) {
            window.closeLmModal();
        }
    });
})();

/**
 * Open a dialog modal with an iframe and a close button
 * @param {string} iframeUrl - The URL to load in the iframe
 * @param {string} modalClass - CSS class for the modal (default: 'popup_dashboard')
 * @param {function} onClose - Optional callback function to call when modal is closed
 */
window.openIframeModal = function(iframeUrl, modalClass, onClose) {
    modalClass = modalClass || 'popup_dashboard';

    const frame = `
        <div class="frame-container">
            <button class="modal-close-btn">&times;</button>
            <div class="frame-loading" style="display:none;"></div>
            <iframe src="${iframeUrl}" width="100%" style="border: none; visibility: hidden;"></iframe>
        </div>
    `;

    window.openLmModal(frame, modalClass);

    const dialog = document.getElementById('lm-modal');
    const iframe = dialog.querySelector('iframe');
    let revealed = false;
    const originalTitle = document.title;
    const loading = dialog.querySelector('.frame-loading');

    const spinnerTimeout = setTimeout(function() {
        if (!revealed && loading) loading.style.display = '';
    }, 500);

    function revealIframe() {
        if (revealed) return;
        revealed = true;
        clearTimeout(spinnerTimeout);
        iframe.style.visibility = 'visible';
        if (loading) loading.style.display = 'none';
        if (modalClass === 'popup_edit') {
            try {
                const iframeTitle = iframe.contentDocument && iframe.contentDocument.title;
                if (iframeTitle) document.title = iframeTitle;
            } catch (_err) {}
        }
    }

    function restoreTitle() {
        if (modalClass === 'popup_edit') document.title = originalTitle;
    }

    iframe.addEventListener('load', revealIframe, { once: true });

    function onIframeMessage(e) {
        if (!e.data || !e.source || e.source !== iframe.contentWindow) return;

        if (e.data.type === 'iframe_resize') {
            revealIframe();
            if (modalClass === 'popup_delete' && e.data.height) {
                const h = e.data.height + 'px';
                iframe.style.height = h;
                const fc = iframe.closest('.frame-container');
                if (fc) fc.style.height = h;
            }
        }

        if (e.data.type === 'dashboard_form_saved') {
            if (e.data.redirect_url) {
                window.location.href = e.data.redirect_url;
            } else {
                window.closeLmModal();
                if (typeof onClose === 'function') setTimeout(onClose, 300);
            }
        }
    }
    window.addEventListener('message', onIframeMessage);

    dialog.querySelector('.modal-close-btn').addEventListener('click', function(e) {
        e.preventDefault();
        window.closeLmModal();
        restoreTitle();
        if (typeof onClose === 'function') onClose();
    });

    dialog.addEventListener('close', function() {
        window.removeEventListener('message', onIframeMessage);
        restoreTitle();
    }, { once: true });
}

// Toggle the mobile sidebar visibility and swap the open/close buttons.
function sidebar_mobile() {
    $('body').toggleClass('is-sidebar-visible');
    $('#sidebar-mobile-open').toggle();
    $('#sidebar-mobile-close').toggle();
}

const tinymceConfig = JSON.parse(document.getElementById('tinymce-config').textContent);

// Initialize TinyMCE on matching textareas; resolves with the editor id once ready.
window.addTinyMCETextarea = function(sel) {
    return new Promise((resolve) => {
        let config = Object.assign({}, tinymceConfig);
        config.selector = sel + ':not(.tinymce-initialized)';
        config.setup = function (editor) {
            editor.on('init', function () {
                editor.getElement().classList.add('tinymce-initialized');
                resolve(editor.id);
            });
        };
        tinymce.init(config);
    });
}

// ========== Init: Headings ==========

// Fit banner/sidebar/header titles with textfill and strip trailing ":" from table header labels.
function initHeadings() {
    $('.association #banner h1').textfill({});
    $('#sidebar h1').textfill({});
    $('#header h1').textfill({});

    // strip trailing ":" from table header labels
    $("th label").each(function() {
        $(this).contents().filter(function() {
            return this.nodeType === 3; // Nodo di testo
        }).each(function() {
            this.nodeValue = this.nodeValue.replace(":", "");
        });
    });
}

// ========== Init: Sidebar ==========

// Wire mobile sidebar open/close toggles, close-on-outside-click, and highlight the active link.
function initSidebar() {
    $('#sidebar-mobile-open, #sidebar-mobile-close').on('click', function(event) {
        sidebar_mobile();
    });

    $('#sidebar-mobile-close').hide();

    $(document).on('click', function(event) {
        if (parseFloat($('#sidebar').css('opacity')) > 0) {
            if (!$(event.target).closest('#sidebar .inner').length) {
                $('body').removeClass('is-sidebar-visible');
            }
        }
    });

    show_sidebar_active();

    var collapseBtn = document.getElementById('sidebar-collapse-btn');
    if (collapseBtn) {
        var sidebar = document.getElementById('sidebar');
        var pageWrapper = document.getElementById('page-wrapper');
        function applySidebarCollapse(collapsed) {
            sidebar.classList.toggle('sidebar-collapsed', collapsed);
            if (pageWrapper) {
                pageWrapper.classList.toggle('sidebar-collapsed', collapsed);
            }
            document.body.classList.toggle('sidebar-collapsed', collapsed);
        }
        if (localStorage.getItem('sidebarCollapsed') === '1') {
            applySidebarCollapse(true);
        }
        collapseBtn.addEventListener('click', function() {
            var collapsed = !sidebar.classList.contains('sidebar-collapsed');
            applySidebarCollapse(collapsed);
            localStorage.setItem('sidebarCollapsed', collapsed ? '1' : '0');
        });
    }
}

// ========== Init: Dropdowns ==========

// Hover fade for dropdown menus, stop button click bubbling, and mark empty menus as "nope".
function initDropdowns() {
    $('.dropdown-button').click(function(event) {
        event.stopPropagation();
    });

    $('.dropdown').on('mouseenter', function() {
        $(this).children('.dropdown-menu').fadeIn(100);
    }).on('mouseleave', function() {
        $(this).children('.dropdown-menu').fadeOut(100);
    });

    $('.dropdown-menu').each(function() {
      if ($(this).children().length == 0) {
        $(this).addClass('nope');
      }
    });
}

// ========== Init: Feature modals ==========

// Open tutorial/feature iframe modals and the feature-description popup via AJAX.
function initFeatureModals() {
    $('a.feature_tutorial').on('mousedown', function(event) {
        event.preventDefault();

        url = url_tutorials + $(this).attr("tut");

        // add iframe get param
        let [base, hash] = url.split('#');
        let [path, query] = base.split('?');
        let params = new URLSearchParams(query || '');
        params.set('in_iframe', '1');
        let newUrl = path + '?' + params.toString();
        if (hash) {
            newUrl += '#' + hash;
        }

        window.openIframeModal(newUrl, 'popup_tutorial');

    });

    $('a.popup-iframe-link').on('click', function(event) {
        event.preventDefault();
        window.openIframeModal($(this).data('iframe-url'), 'popup_tutorial');
    });

    $('.feature_checkbox a').click(function(event) {
        event.preventDefault();

        request = $.ajax({
            url: url_feature_description,
            method: "POST",
            data: {'fid': $(this).attr("feat")},
            datatype: "json",
        });

        request.done(function(data) {
            if (data["res"] != 'ok') return;

            window.openLmModal(data['txt'], 'popup');

        });

        return false;
    });
}

// ========== Init: Menu ==========

// Accordion behavior for menu openers and removal of empty menu lists/cells.
function initMenu() {
    $menu_openers = $('#menu .opener');

    // Openers.
    $menu_openers.each(function() {

        var $this = $(this);

        $this.on('click', function(event) {

            // Prevent default.
                event.preventDefault();

            // Toggle.
                $menu_openers.not($this).removeClass('active');
                $this.toggleClass('active');

            // Trigger resize (sidebar lock).
                $(window).triggerHandler('resize.sidebar-lock');

        });

    });

    $('#menu .links ul:empty ').hide();

    $('#menu .links ul:not(:has(*))').parent().remove();

    $('.links td:not(:has(*))').parent().remove();
}

// ========== Init: Flash messages ==========

// Fade flash messages in, then auto-dismiss them after 5 seconds.
function initFlashMessages() {
    $('.hideMe').fadeIn(200);

    setTimeout(function() {
        $('.hideMe').fadeOut(200);
    }, 5000); // <-- time in milliseconds
}

// ========== Init: Tooltips ==========

// Init qtip tooltips (prod only) plus character and generic hover tooltips.
function initTooltips() {
    /* QTIP TOOLTIP */
    if (window.enviro == "prod") {
        lm_tooltip();
        add_icon_tooltips();
    }

    reload_has_char();

    reload_has_tooltip();
}

// ========== Init: Date pickers ==========

// Attach datetimepicker widgets to date_p / datetime_p / time_p inputs.
function initDatepickers() {
    $(':input[type="date_p"]').datetimepicker({
        format:'Y-m-d',
        timepicker: false,
        scrollMonth : false,
        scrollInput : false
    });

    $(':input[type="datetime_p"]').datetimepicker({
        format:'Y-m-d H:i',
        scrollMonth : false,
        scrollInput : false
    });

    $(':input[type="time_p"]').datetimepicker({
        format:'H:i',
        datepicker: false,
        scrollInput : false
    });
}

// ========== Init: Slug field ==========

// Sanitize manual slug input and auto-generate the slug from the name until the user edits it.
function initSlugField() {
    let slugTouched = false;
    let slugTimeout;

    $('#slug').on('input', function (e) {
        slugTouched = true;

        let v = $(this).val();
        var sl = new RegExp('[^a-z0-9]');
        if (sl.test(v)) {
            $('.slug_war').fadeIn(200);

            clearTimeout(slugTimeout);
            slugTimeout = setTimeout(function() {
                $('.slug_war').fadeOut(200);
            }, 3000);

            v = v.replace(sl, '');
            $(this).val(v);
        }

        $(this).trigger('slug:changed', [v]);
    });

    $('#id_name, #id_form1-name').on('input', function (e) {
        if (!slugTouched) {
            let nameVal = $(this).val();
            let autoSlug = slugify(nameVal);
            autoSlug = autoSlug.replaceAll('-', '');
            $('#slug').val(autoSlug).trigger('slug:changed', [autoSlug]);
        }
    });
}

// ========== Init: Toggles ==========

// Show/hide target blocks via .my_toggle, scrolling into view and tracking select state.
function initToggles() {
    $(document).on("click", ".my_toggle", function() {
        var k = $(this).attr("tog");
        var el =  $("." + k);
        el.toggle();

         if (el.is(":visible")) {
             var elements = document.getElementsByClassName(k);

             if (elements.length > 0 && ! $(this).hasClass("no_jump") && !window.disable_jump)  {
                window.jump_to('.' + k);
            }
            $(this).addClass('select');
        } else {
            $(this).removeClass('select');
        }

        return false;

    });
}

// ========== Init: Datatable links / delete confirm ==========

// Suppress link navigation during bulk mode and add native delete confirmation outside v21 modals.
function initDatatableLinks() {
    // dont' follow links if bulk is active
    $('.go_datatable').on('click', 'a', function(e) {
        if ($('#main_bulk').is(':visible')) {
            e.preventDefault();
            e.stopPropagation();
        }
    });

    // Confirmation for delete icons (fa-trash). On v21 manage pages the confirmation
    // is handled by the iframe modal (see replaceNewUrl), so skip the native confirm.
    $(document).on('click', 'a:has(i.fa-trash), a:has(i.fa-solid.fa-trash), a:has(i.fas.fa-trash)', function(e) {
        const inDatatable = $(this).closest('table.go_datatable, table.pagin_datatable').length > 0;
        if (inDatatable && $('body').hasClass('new_v21') && $('body').hasClass('manage')) {
            return;
        }
        if (!window.lmTesting && !confirm('Are you sure you want to delete this item?')) {
            e.preventDefault();
            e.stopPropagation();
            return false;
        }
    });
}

// ========== Init: Popups ==========

// Open inline .show_popup content in the modal and wire AJAX post_popup handlers.
function initPopups() {
    $(document).on("click", ".show_popup", function() {
        num = $(this).attr("pop");
        tp = $(this).attr("fie");

        el = $('#' + num).find('.popup_text.' + tp).first();

        window.openLmModal(el.html(), 'popup');

        $('#lm-modal').scrollTop( 0 );

        reload_has_char();

        return false;
    });

    post_popup();
}

// ========== Init: Table search ==========

// Live filter writing-table rows against the #search_tbl input text.
function initTableSearch() {
    $('#search_tbl').on('input', function() {
        key = $(this).val();
        $('table.writing tr').each(function( index ) {
            var tx = "";
            $(this).children().each( function () {
              tx += " " + $(this).html();
            });

            if (tx.toLowerCase().includes(key.toLowerCase())) {
                $(this).show(300);
            } else {
                $(this).hide(300);
            }
        });

    });
}

// ========== Init: Fade-ins ==========

// Fade in the main layout regions (content, topbar, sidebar, footer) on load.
function initFadeIns() {
    $('#one .inner').fadeIn(100);
    $('#topbar .inner').fadeIn(100);
    $('#sidebar .inner').fadeIn(100);
    $('#footer .inner').fadeIn(100);
}

// ========== Init: Misc ==========

// Leftover setup: hide empty info box, resize fields, clipboard buttons, select chevrons,
// conditional fields, new-url handlers, and removal of empty page-info.
function initMisc() {
    if ($('.info').is(':empty')) {
        $('.info').hide();
    }

    resize_fields();

    copyClipboardButton();

    setSelectChevronColor();

    setupConditionalFields();

    replaceNewUrl();

    // remove empty pageinfo
    var $pageInfo = $('#page-info');
    if ($pageInfo.length && !$pageInfo.attr('qtip').trim()) {
        $pageInfo.remove();
    }
}

$(document).ready(function() {

    // Layout / chrome
    initHeadings();
    initSidebar();
    initDropdowns();
    initMenu();
    initFadeIns();

    // Notifications
    initFlashMessages();
    initTooltips();

    // Forms / inputs
    initDatepickers();
    initSlugField();

    // Interactions
    initToggles();
    initFeatureModals();
    initPopups();
    initTableSearch();

    // Tables
    initDatatableLinks();
    data_tables();

    // Misc
    initMisc();

    window._lmReady = true;
    $(document).trigger("lm_ready");
});

// Route "new"/edit/delete table links through iframe modals on v21 manage pages.
function replaceNewUrl() {
    $(document).on('click', 'a.form-new', function(event) {
        event.preventDefault();
        let href = $(this).attr('href');
        let newUrl;
        if (href && href !== '#') {
            newUrl = href;
        } else {
            let currentUrl = window.location.href;
            let cleanedUrl = currentUrl.split('#')[0];
            newUrl = cleanedUrl + 'new/';
        }
        if ($('body').hasClass('new_v21') && $('body').hasClass('manage')) {
            openIframeModal(newUrl + '?frame=1', 'popup_edit', refreshDatatables);
        } else {
            window.location.href = newUrl;
        }
    });

    if ($('body').hasClass('new_v21') && $('body').hasClass('manage')) {
        $(document).on('click', 'table.go_datatable a:has(i.fa-edit), table.pagin_datatable a:has(i.fa-edit)', function(e) {
            e.preventDefault();
            openIframeModal(this.href + '?frame=1', 'popup_edit', refreshDatatables);
            return false;
        });

        $(document).on('click', 'table.go_datatable a:has(i.fa-trash), table.pagin_datatable a:has(i.fa-trash)', function(e) {
            e.preventDefault();
            e.stopPropagation();
            openIframeModal(this.href + '?frame=1', 'popup_delete', refreshDatatables);
            return false;
        });
    }
}

// Reload datatable contents after a modal save, re-fetching the page and patching tables/headings.
function refreshDatatables() {
    $('table.pagin_datatable').each(function() {
        const tableId = $(this).attr('id');
        if (tableId && window.datatables && window.datatables[tableId]) {
            window.datatables[tableId].ajax.reload(null, false);
        }
    });

    $.get(window.location.href, function(html) {
        const $newDoc = $($.parseHTML(html));
        const $newTables = $newDoc.find('table.go_datatable');
        const savedStates = {};
        let $emptyAnchor = null;

        // page was empty (no tables) but now has content: replace the whole content wrapper
        if (!$('table.go_datatable').length && $newTables.length) {
            const $page = $('[class^="page_"], [class*=" page_"]').first();
            const $newPage = $newDoc.find('[class^="page_"], [class*=" page_"]').first();
            if ($page.length && $newPage.length) {
                $page.html($newPage.html());
                // rebuild column index map from the freshly injected table headers
                if (typeof window.buildHideColumnsIndexMap === 'function') window.buildHideColumnsIndexMap();
                // do NOT suppress trigger togs: apply default column visibility (hidden columns)
                data_tables();
                if (typeof window.reloadActiveQuestions === 'function') window.reloadActiveQuestions();
                if (typeof window.applyColumnToggles === 'function') window.applyColumnToggles();
                resize_fields();
                window._datatablesRefreshCount = (window._datatablesRefreshCount || 0) + 1;
                return;
            }
        }

        // nearest heading right before a table (skipping <hr>), or empty set
        function headingFor($table) {
            let node = $table[0].previousElementSibling;
            while (node && node.tagName === 'HR') node = node.previousElementSibling;
            return node && node.tagName === 'H2' ? $(node) : $();
        }

        $('table.go_datatable').each(function(index) {
            const $oldTable = $(this);
            const tableId = $oldTable.attr('id');

            if (tableId && window.datatables && window.datatables[tableId]) {
                const dt = window.datatables[tableId];
                savedStates[tableId] = {
                    order: dt.order(),
                    search: dt.search(),
                    colSearches: dt.columns().search().toArray(),
                };
                dt.destroy();
                delete window.datatables[tableId];
            }

            let $newTable = tableId ? $newDoc.find('#' + tableId) : $();
            if (!$newTable.length) $newTable = $newTables.eq(index);

            // heading (with element count) tied to this table, if present right before it
            const $oldHeading = headingFor($oldTable);

            const newRows = $newTable.length ? $newTable.find('tbody > tr').length : 0;
            if ($newTable.length && newRows > 0) {
                $oldTable.find('thead').html($newTable.find('thead').html());
                $oldTable.find('tbody').html($newTable.find('tbody').html());
                $oldTable.show();
                // refresh heading (counts may have changed)
                const $newHeading = $newTable.length ? headingFor($newTable) : $();
                if ($oldHeading.length && $newHeading.length) {
                    $oldHeading.html($newHeading.html());
                }
            } else {
                // no rows left in new page (group/last element deleted): remove table and heading
                const $anchorRef = $oldHeading.length ? $oldHeading : $oldTable;
                if (!$emptyAnchor) $emptyAnchor = $('<span>').insertBefore($anchorRef);
                // remove a leading <hr> separator if it belongs to this block
                const prev = $anchorRef[0].previousElementSibling;
                if (prev && prev.tagName === 'HR') prev.remove();
                $oldHeading.remove();
                $oldTable.remove();
            }
        });

        const $newNoElements = $newDoc.find('.no-elements-available');
        if (!$newNoElements.length) {
            $('.no-elements-available').hide();
        } else if (!$('.no-elements-available').length) {
            // new page shows the empty placeholder but current page has none: inject it
            if ($emptyAnchor) {
                $emptyAnchor.replaceWith($newNoElements);
            } else {
                $('table.pagin_datatable, table.go_datatable').first().after($newNoElements);
            }
        } else {
            $('.no-elements-available').show();
        }
        if ($emptyAnchor) $emptyAnchor.remove();

        // refresh summary sections that hold derived lists/counts (e.g. registrations email lists)
        const $oldSummary = $('#registrations_summary');
        if ($oldSummary.length) {
            const $newSummary = $newDoc.find('#registrations_summary');
            if ($newSummary.length) {
                $oldSummary.html($newSummary.html());
            } else {
                $oldSummary.remove();
            }
        }

        window._datatablesSavedState = savedStates;
        window._suppressTriggerTogs = true;
        data_tables();
        delete window._datatablesSavedState;
        delete window._suppressTriggerTogs;

        if (typeof window.reloadActiveQuestions === 'function') {
            window.reloadActiveQuestions();
        }
        if (typeof window.applyColumnToggles === 'function') {
            window.applyColumnToggles();
        }
        resize_fields();
        window._datatablesRefreshCount = (window._datatablesRefreshCount || 0) + 1;
    });
}

/**
 * Sets up conditional field visibility based on data attributes.
 * Fields with data-conditional-controller control visibility of fields
 * with data-conditional-show that match the controller's value.
 */
function setupConditionalFields() {
    $('[data-conditional-controller]').each(function() {
        var $controller = $(this);
        var controllerName = $controller.attr('data-conditional-controller');

        function updateVisibility() {
            var selectedValue = $controller.val();

            // Find all fields that depend on this controller
            $('[data-conditional-show]').each(function() {
                var $field = $(this);
                var showForValue = $field.attr('data-conditional-show');
                var $row = $field.closest('tr');

                if (selectedValue === showForValue) {
                    $row.show();
                } else {
                    $row.hide();
                }
            });
        }

        // Initial state
        updateVisibility();

        // Update on change
        $controller.on('change', updateVisibility);
    });
}

// Build an inline SVG chevron tinted with the theme color and apply it as the select background.
function setSelectChevronColor() {
  const priRgb = getComputedStyle(document.body)
    .getPropertyValue('--ter-rgb')
    .trim();

  const svg = `
<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 40 40">
  <path d="M9.4,12.3l10.4,10.4l10.4-10.4c0.2-0.2,0.5-0.4,0.9-0.4c0.3,0,0.6,0.1,0.9,0.4l3.3,3.3c0.2,0.2,0.4,0.5,0.4,0.9
  c0,0.4-0.1,0.6-0.4,0.9L20.7,31.9c-0.2,0.2-0.5,0.4-0.9,0.4c-0.3,0-0.6-0.1-0.9-0.4L4.3,17.3c-0.2-0.2-0.4-0.5-0.4-0.9
  c0-0.4,0.1-0.6,0.4-0.9l3.3-3.3c0.2-0.2,0.5-0.4,0.9-0.4S9.1,12.1,9.4,12.3z"
  fill="rgba(${priRgb},0.725)"/>
</svg>`;

  const encoded = encodeURIComponent(svg)
    .replace(/'/g, "%27")
    .replace(/"/g, "%22");

    $('select:not(.dt-input)').css(
      'background-image',
      `url("data:image/svg+xml,${encoded}")`
    );
}

// Mark the sidebar link matching the current URL as selected and scroll it into center view.
function show_sidebar_active() {
    // set select on sidebar, pick only the most specific match
    var currentUrl = window.location.pathname.replace(/\/$/, '');
    var bestMatch = null;
    var bestLen = -1;

    $('.sidebar-link').each(function() {
      var linkHref = $(this).attr('href').replace(/\/$/, '');
      var safeHref = linkHref.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      var regex = new RegExp('^' + safeHref + '(?:$|\\/.*)');

      var match;
      if (linkHref.endsWith('manage'))
        match = currentUrl.endsWith('manage');
      else
        match = regex.test(currentUrl);

      if (match && linkHref.length > bestLen) {
        bestMatch = this;
        bestLen = linkHref.length;
      }
    });

    if (bestMatch) $(bestMatch).addClass('select');

    // scroll sidebar to center the active link
    var $active = $('.sidebar-link.select').first();
    if ($active.length) {
      var $sidebar = $('#sidebar .inner');
      var sidebarScrollTop = $sidebar.scrollTop();
      var sidebarHeight = $sidebar.height();
      var itemTop = $active.offset().top - $sidebar.offset().top + sidebarScrollTop;
      var itemHeight = $active.outerHeight();
      $sidebar.scrollTop(itemTop - (sidebarHeight - itemHeight) / 2);
    }

}

// Initialize client-side (go_datatable) and server-side (pagin_datatable) DataTables,
// applying sort/visibility config, row reorder, tooltips, and saved state.
function data_tables() {
    window.datatables = window.datatables || {};

    $('table.go_datatable').each(function() {
        const $table = $(this);

        const $tbody = $table.find('tbody');
        const rowCount = $tbody.find('tr').length;

        if (rowCount === 0) {
            $table.hide();
            return;
        }

        // assign random id
        if (!$table.attr('id')) {
            const randomId = 'table-' + Math.random().toString(36).substr(2, 9);
            $table.attr('id', randomId);
        }

        const tableId = $table.attr('id');

        var thList = $table.find('thead th');
        var disable_sort_columns = [];

        // disable sort for empty thead th
        thList.each(function (index) {
            if ($(this).text().trim() === '') {
                disable_sort_columns.push(index);
            }
        });

        let table_no_header_cols = $table.attr('no_header_cols');
        if (table_no_header_cols) {
            if (table_no_header_cols === "all") {
                var thList = $table.find('thead th');
                var totalColumns = thList.length;
                disable_sort_columns = Array.from({length: totalColumns}, (_, i) => i);
            } else {
                disable_sort_columns = disable_sort_columns.concat(
                    JSON.parse(table_no_header_cols)
                );
            }
        }

        let hide_columns = [];
        if (window.hideColumnsIndexMap && typeof window.hideColumnsIndexMap === 'object') {
            Object.keys(window.hideColumnsIndexMap).forEach(function(key) {
                var value = window.hideColumnsIndexMap[key];
                hide_columns.push(...value);
            });
        }

        var is_reorder = $table.hasClass('row_reorder');
        var full_layout = !is_reorder && rowCount >= 10;
        var no_buttons = $table.attr('no_buttons') !== undefined;

        var dtConfig = {
            scrollX: true,
            responsive: window.enviro === 'prod',
            stateSave: false,
            paging: full_layout,
            layout: full_layout
                ? (no_buttons
                    ? { topStart: null, topEnd: null, bottomStart: 'pageLength', bottomEnd: 'paging' }
                    : { topStart: null, topEnd: null, bottomStart: 'pageLength', bottomEnd: 'paging', bottom2: { buttons: ['copy', 'csv', 'excel', 'pdf', 'print'] } })
                : { topStart: null, topEnd: null, bottomStart: null, bottomEnd: null },
            columnControl: ['order', 'searchDropdown'],
            lengthMenu: [[25, 50, 100, 250, 500, 1000], [25, 50, 100, 250, 500, 1000]],
            order: [],
            ordering: {
                indicators: false,
                handler: false
            },
            columnDefs: [
                { orderable: false, targets: disable_sort_columns },
                { visible: false, targets: hide_columns },
                { columnControl: [], targets: disable_sort_columns }
            ],
            rowCallback: function (row, data) {
              $('td', row).each(function (i) {
                var tip = $(this).attr('tooltip');
                if (tip) {
                  $(this).attr('title', tip);
                }
              })
            }
        };

        if (is_reorder) {
            dtConfig.rowReorder = { selector: 'td.reorder-handle', update: false };
        }

        const table = new DataTable('#' + tableId, dtConfig);

        if (is_reorder) {
            var reorderUrl = $table.data('reorder-url');
            var reorderModel = $table.data('reorder-model');
            table.on('row-reorder', function() {
                var uuids = [];
                $table.find('tbody tr[id]').each(function() {
                    uuids.push($(this).attr('id'));
                });
                if (uuids.length && reorderUrl && reorderModel) {
                    $.ajax({
                        url: reorderUrl,
                        type: 'POST',
                        contentType: 'application/json',
                        data: JSON.stringify({ model: reorderModel, uuids: uuids })
                    });
                }
            });
        }

        table.on('draw.dt', function() {
            // Add tooltips to edit icons first
            if (window.enviro == "prod") {
                add_icon_tooltips();
            }

            // Then handle any remaining qtip attributes
            $('a[qtip]').each(function() {
                if (!$(this).data('qtip-initialized')) {
                    $(this).qtip({
                        content: { text: $(this).attr('qtip') },
                        style: { classes: 'qtip-dark qtip-rounded qtip-shadow' },
                        hide: { effect: function(offset) { $(this).fadeOut(500); } },
                        show: { effect: function(offset) { $(this).fadeIn(500); } },
                        position: { my: 'top center', at: 'bottom center' }
                    });
                    $(this).data('qtip-initialized', true);
                }
            });
        });

        for (const index of hide_columns) {
            var column = table.column(index);
            column.visible(false);
        };

        window.datatables[tableId] = table;

        if (window._datatablesSavedState && window._datatablesSavedState[tableId]) {
            const state = window._datatablesSavedState[tableId];
            let needDraw = false;
            if (state.search) { table.search(state.search); needDraw = true; }
            if (state.colSearches) {
                state.colSearches.forEach(function(colSearch, i) {
                    if (colSearch) { table.column(i).search(colSearch); needDraw = true; }
                });
            }
            if (state.order && state.order.length) { table.order(state.order); needDraw = true; }
            if (needDraw) table.draw(false);
        }
    });

    if (Array.isArray(window.trigger_togs) && !window._suppressTriggerTogs) {
        window.trigger_togs.forEach(function(togValue) {
            if (togValue.startsWith('.') || togValue.startsWith('#')) {
                $(togValue).each(function() {
                    this.dispatchEvent(new MouseEvent('click', { bubbles: true }));
                });
            } else {
                if (togValue == '#load_accounting') {
                    document.querySelector('#load_accounting').dispatchEvent(new MouseEvent('click', { bubbles: true }));
                } else {
                    $('a.table_toggle[tog="' + togValue + '"]').each(function() {
                        this.dispatchEvent(new MouseEvent('click', { bubbles: true }));
                    });
                }
            }
        });
    }

    $('table.pagin_datatable').each(function() {
        const $table = $(this);

        // assign random id
        if (!$table.attr('id')) {
            const randomId = 'table-' + Math.random().toString(36).substr(2, 9);
            $table.attr('id', randomId);
        }
        const tableId = $table.attr('id');

        if (window.datatables && window.datatables[tableId]) {
            return;
        }

        window._datatablesInitPending = (window._datatablesInitPending || 0) + 1;

        const url = $table.attr('url');

        var thList = $table.find('thead th');
        var disable_sort_columns = [];

        // disable sort for empty thead th
        thList.each(function (index) {
            if ($(this).text().trim() === '') {
                disable_sort_columns.push(index);
            }
        });

        const table = new DataTable('#' + tableId, {
            lengthMenu: [[25, 50, 100, 250, 500, 1000, 2500, 5000, 10000], [25, 50, 100, 250, 500, 1000, 2500, 5000, 10000]],
            ajax: {
                url: url,
                type: 'POST'
            },
            serverSide: true,
            stateSave: false,
            columnControl: [
                {
                    target: 0,
                    content: ['order', 'searchDropdown']
                },
            ],
            ordering: {
                indicators: false,
                handler: false
            },
            columnDefs: [
                { orderable: false, targets: disable_sort_columns },
                { searcheable: false, targets: disable_sort_columns },
                { columnControl: [], targets: disable_sort_columns }
            ],
            layout: { topStart: null, topEnd: null, bottomStart: 'pageLength', bottomEnd: 'paging', bottom2: { buttons: ['copy', 'csv', 'excel', 'pdf', 'print'] } },
            /*
            initComplete: function () {
                this.api()
                    .columns()
                    .every(function () {
                        let column = this;
                        let title = column.footer().textContent;

                        // Create input element
                        let input = document.createElement('input');
                        input.placeholder = title;
                        column.footer().replaceChildren(input);

                        // Event listener for user input
                        input.addEventListener('keyup', () => {
                            if (column.search() !== this.value) {
                                column.search(input.value).draw();
                            }
                        });
                    });
            }
            */
        });

        window.datatables = window.datatables || {};
        window.datatables[tableId] = table;

        table.one('init.dt', function() {
            window._datatablesInitPending = Math.max(0, (window._datatablesInitPending || 0) - 1);
        });

        table.on('draw.dt', function() {
            // Add tooltips to edit icons first
            if (window.enviro == "prod") {
                add_icon_tooltips();
            }

            // Then handle any remaining qtip attributes
            $('a[qtip]').each(function() {
                if (!$(this).data('qtip-initialized')) {
                    $(this).qtip({
                        content: { text: $(this).attr('qtip') },
                        style: { classes: 'qtip-dark qtip-rounded qtip-shadow' },
                        hide: { effect: function(offset) { $(this).fadeOut(500); } },
                        show: { effect: function(offset) { $(this).fadeIn(500); } },
                        position: { my: 'top center', at: 'bottom center' }
                    });
                    $(this).data('qtip-initialized', true);
                }
            });
        });
    });
}

// Wire .post_popup clicks to POST for popup content and show the result in the modal.
function post_popup() {
    $(document).on('click', '.post_popup', function (e) {

        start_spinner();

        request = $.ajax({
            url: window.location,
            method: "POST",
            data: { popup: 1, idx: $(this).attr("pop"), tp: $(this).attr("fie") },
            datatype: "json",
        });

        request.done(function(res) {
            stop_spinner();

            if (res.k == 0) return;

            window.openLmModal(res.v, 'popup');

			reload_has_char();

            $('#lm-modal').scrollTop( 0 );
            $('#lm-modal .hide').hide();
        });

        request.fail(function(res) {
            stop_spinner();
        });

        return false;
    });
}

// (Re)bind character preview qtip tooltips to .has_show_char elements within parent.
function reload_has_char(parent='') {

    $(parent + ' ' + '.has_show_char').each(function() {

        $(this).qtip({
            content: {
                text: $(this).next('span')
            }, style: {
                classes: 'qtip-dark qtip-rounded qtip-shadow qtip-char'
            }, hide: {
                effect: function(offset) {
                    $(this).fadeOut(500);
                }
            }, show: {
                effect: function(offset) {
                    $(this).fadeIn(500);
                }
            }, position: {
                my: 'top left',
                at: 'bottom center',
            }
        });
    });

}

// Bind the various qtip tooltip styles: .lm_tooltip, .explain-icon, data-tooltip, and a[qtip].
function lm_tooltip() {

    $('.lm_tooltip').each(function() {

        $(this).qtip({
            content: {
                text: $(this).children('.lm_tooltiptext')
            }, style: {
                classes: 'qtip-dark qtip-rounded qtip-shadow qtip-lm'
            }, hide: {
                effect: function(offset) {
                    $(this).fadeOut(500);
                }
            }, show: {
                effect: function(offset) {
                    $(this).fadeIn(500);
                }
            }, position: {
                my: 'top center',
                at: 'bottom center',
            }
        });
    });

 $('.explain-icon').qtip({
        content: {
            text: function() {
                return $(this).parent().attr('descr');
            }
        },
        style: {
            classes: 'qtip-dark qtip-rounded qtip-shadow qtip-lm'
        },
        show: {
            event: 'click mouseenter',
            solo: true
        },
        hide: {
            event: 'mouseleave unfocus'
        },
        position: {
            my: 'top left',
            at: 'bottom center',
            viewport: window,
            adjust: { method: 'flipinvert shift' },
            target: function() {
                return $(this).prevAll('.sidebar-link').first();
            }
        }
    });

    $('[data-tooltip!=""]').qtip({
        content: {
            attr: 'data-tooltip'
        }
    });

    $('a[qtip]').each(function() {
        $(this).qtip({
            content: {
                text: $(this).attr('qtip')
            },
            style: {
                classes: 'qtip-dark qtip-rounded qtip-shadow'
            },
            hide: {
                effect: function(offset) {
                    $(this).fadeOut(500);
                }
            },
            show: {
                effect: function(offset) {
                    $(this).fadeIn(500);
                }
            },
            position: {
                my: 'top center',
                at: 'bottom center'
            }
        });
    });
}


// (Re)bind generic qtip tooltips to .has_show_tooltip elements within parent.
function reload_has_tooltip(parent='') {

    $(parent + ' ' + '.has_show_tooltip').each(function() {

        $(this).qtip({
            content: {
                text: $(this).next('span')
            }, style: {
                classes: 'qtip-dark qtip-rounded qtip-shadow'
            }, hide: {
                effect: function(offset) {
                    $(this).fadeOut(500);
                }
            }, show: {
                effect: function(offset) {
                    $(this).fadeIn(500);
                }
            }, position: {
                my: 'top right',
                at: 'bottom center',
            }
        });
    });

}

// Add translated qtip tooltips to edit/up/down/trash action icons that lack one.
function add_icon_tooltips() {
    // Dictionary mapping icon classes to their tooltip texts
    var iconTooltips = {
        'fa-edit': window['icon_texts']['edit'],
        'fa-arrow-up': window['icon_texts']['up'],
        'fa-arrow-down': window['icon_texts']['down'],
        'fa-trash': window['icon_texts']['delete']
    };

    // Process each icon type
    Object.keys(iconTooltips).forEach(function(iconClass) {
        var defaultText = iconTooltips[iconClass];

        // Find all icons with this class (supporting both .fa-* and .fas.fa-*)
        $('i.' + iconClass + ', i.fa-solid.' + iconClass + ', i.fas.' + iconClass).each(function() {
            var $icon = $(this);
            var $link = $icon.closest('a');

            // Only add tooltip if the link doesn't already have qtip attribute and not already initialized
            if ($link.length && !$link.attr('qtip') && !$link.data('qtip-initialized')) {
                // Get translation text from data attribute or use default
                var dataAttr = iconClass.replace('fa-', '') + '-tooltip';
                var tooltipText = $link.data(dataAttr) || defaultText;
                $link.attr('qtip', tooltipText);

                // Initialize qtip for this link
                $link.qtip({
                    content: {
                        text: tooltipText
                    },
                    style: {
                        classes: 'qtip-dark qtip-rounded qtip-shadow'
                    },
                    hide: {
                        effect: function(offset) {
                            $(this).fadeOut(500);
                        }
                    },
                    show: {
                        effect: function(offset) {
                            $(this).fadeIn(500);
                        }
                    },
                    position: {
                        my: 'top center',
                        at: 'bottom center'
                    }
                });

                $link.data('qtip-initialized', true);
            }
        });
    });
}





// POST the chosen UI language to the server.
function selectLanguage(lang) {
    xhttp.open("POST", set_language_url, true);
    xhttp.setRequestHeader("Content-type", "application/x-www-form-urlencoded");
    xhttp.send("language=" + lang);
}

// Scale writing-table cell font size down as text length grows (excluding popup text).
function resize_fields() {
    $(".writing td").each(function( index ) {

        var textLength = stripHTML($(this).text()).length;

       $(this).find('.popup_text').each(function () {
           textLength -= stripHTML($(this).text()).length;
        });

        fontSize = Math.max(50, Math.round(100 - textLength / 7));

        $(this).css('font-size', fontSize + '%');
    });

}

// Return an HTML-escaped (XSS-safe) version of the input string.
function stripHTML(dirtyString) {
  var container = document.createElement('div');
  var text = document.createTextNode(dirtyString);
  container.appendChild(text);
  return container.innerHTML; // innerHTML will be a xss safe string
}

// String.format/f: replace {0}, {1}, ... placeholders with the given arguments.
String.prototype.format = String.prototype.f = function() {
    var s = this,
        i = arguments.length;

    while (i--) {
        s = s.replace(new RegExp('\\{' + i + '\\}', 'gm'), arguments[i]);
    }
    return s;
};

// Convert a string into a URL-safe slug (lowercase, accents stripped, hyphen-separated).
function slugify(str) {
  return String(str)
    .normalize('NFKD') // split accented characters into their base characters and diacritical marks
    .replace(/[\u0300-\u036f]/g, '') // remove all the accents, which happen to be all in the \u03xx UNICODE block.
    .trim() // trim leading or trailing whitespace
    .toLowerCase() // convert to lowercase
    .replace(/[^a-z0-9 -]/g, '') // remove non-alphanumeric characters
    .replace(/\s+/g, '-') // replace spaces with hyphens
    .replace(/-+/g, '-'); // remove consecutive hyphens
}

// Fallback String.format polyfill if not already defined above.
if (!String.prototype.format) {
  String.prototype.format = function() {
    var args = arguments;
    return this.replace(/{(\d+)}/g, function(match, number) {
      return typeof args[number] != 'undefined'
        ? args[number]
        : match
      ;
    });
  };
}

// Copy a link to the clipboard on .copy-link-btn click, with temporary check-icon feedback.
function copyClipboardButton() {
    // Copy link to clipboard functionality (jQuery)
    $(document).on('click', '.copy-link-btn', function (e) {
        e.preventDefault();

        const $btn = $(this);
        const url = window.location.origin + $btn.data('url');

        navigator.clipboard.writeText(url).then(function () {
            const $icon = $btn.find('i');
            const originalClass = $icon.attr('class');

            $icon.attr('class', 'fa-solid fa-check');
            $btn.css('color', '#28a745');

            setTimeout(function () {
                $icon.attr('class', originalClass);
                $btn.css('color', '');
            }, 2000);
        }).catch(function (err) {
            console.error('Failed to copy:', err);
        });
    });

    $('.opt-card-desc').each(function () {
        var len = $(this).text().trim().length;
        var size = len < 60 ? '0.85em' : len < 120 ? '0.75em' : len < 200 ? '0.65em' : '0.55em';
        $(this).css('font-size', size);
    });

}

});
