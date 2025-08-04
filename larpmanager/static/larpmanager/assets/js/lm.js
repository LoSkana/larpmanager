$(".hide:visible").hide();

window.addEventListener('DOMContentLoaded', function() {

// uniform cookies # TODO remove
document.cookie.split(";").forEach(c => {
    const [name, value] = c.trim().split("=");
    if (name === "csrftoken") {
        document.cookie = `csrftoken=${value}; path=/; domain=${location.hostname};`;
        document.cookie = `csrftoken=; path=/; domain=.larpmanager.com; expires=Thu, 01 Jan 1970 00:00:00 UTC;`;
    }
});

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


function sidebar_mobile() {
    $('body').toggleClass('is-sidebar-visible');
    $('#sidebar-mobile-open').toggle();
    $('#sidebar-mobile-close').toggle();
}


$(document).ready(function() {

    $('#banner h1').textfill({
    });

    $('#sidebar h1').textfill({
    });

    $('#header h1').textfill({
    });

    $("th label").each(function() {
        $(this).contents().filter(function() {
            return this.nodeType === 3; // Nodo di testo
        }).each(function() {
            this.nodeValue = this.nodeValue.replace(":", "");
        });
    });

    // Sidebar
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

    $('.dropdown-button').click(function(event) {
        event.stopPropagation();
    });

    $('.dropdown').on('mouseenter', function() {
        $(this).children('.dropdown-menu').fadeIn(100);
    }).on('mouseleave', function() {
        $(this).children('.dropdown-menu').fadeOut(100);
    });

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

        frame = "<iframe src='{0}' width='100%' height='100%'></iframe>".format(newUrl);

        uglipop({class:'popup_tutorial', source:'html', content: frame});

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

            uglipop({class:'popup', source:'html', content: data['txt']});

        });

        return false;
    });

    setTimeout(() => {
    // set select on sidebar
    var currentUrl = window.location.pathname.replace(/\/$/, '');
    $('.sidebar-link').each(function() {
        var linkHref = $(this).attr('href').replace(/\/$/, '');
        var regex = new RegExp('^' + linkHref + '(?:\\/(\\d+|edit\\/\\d+))?\\/?$');
        if (regex.test(currentUrl)) {
            $(this).addClass('select');
        }
    });
    }, 100);

    // Menu.
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

    $('.hideMe').fadeIn(200);

    setTimeout(function() {
        $('.hideMe').fadeOut(200);
    }, 5000); // <-- time in milliseconds

    $('#menu .links ul:empty ').hide();

    $('#menu .links ul:not(:has(*))').parent().remove();

    $('.links td:not(:has(*))').parent().remove();

    /* QTIP TOOLTIP */

    $('[data-tooltip!=""]').qtip({
        content: {
            attr: 'data-tooltip'
        }
    });

    lm_tooltip();

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

    $('#slug').on('input', function (e) {
        v = $(this).val();
        var sl = new RegExp('[^a-z0-9]');
        if (sl.test(v)) {
            $('.slug_war').fadeIn(200);

            setTimeout(function() {
                $('.slug_war').fadeOut(200);
            }, 3000);

            v = v.replace(sl, '');
            $(this).val(v);
        }
    });

    reload_has_char();

    reload_has_tooltip();

    $(document).on("click", ".my_toggle", function() {
        var k = $(this).attr("tog");
        var el =  $("." + k);
        el.toggle();

         if (el.is(":visible")) {
             var elements = document.getElementsByClassName(k);

             if (elements.length > 0 && ! $(this).hasClass("no_jump") && !window.disable_jump)  {
                jump_to(elements[0]);
            }
            $(this).addClass('select');
        } else {
            $(this).removeClass('select');
        }

        window.syncColumnWidths();
        return false;

    });

    if (Array.isArray(window.trigger_togs)) {
        window.trigger_togs.forEach(function(togValue) {
            if (togValue.startsWith('.') || togValue.startsWith('#')) return;
            $('a.my_toggle[tog="' + togValue + '"]').each(function() {
                this.dispatchEvent(new MouseEvent('click', { bubbles: true }));
            });
        });
    }

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

    // table_csv();

    resize_fields();

    // resize_title();

    $('.tablesorter').tablesorter();

    $('.delete').click(function(){
        return confirm('Are you sure?');
    });

    $('.show_popup').on( "click", function() {
        num = $(this).attr("pop");
        tp = $(this).attr("fie");

        el = $('#' + num).find('.popup_text.' + tp).first();

        uglipop({class:'popup', //styling class for Modal
            source:'html',
            content: el.html()});

        $('.popup').scrollTop( 0 );

        reload_has_char();

        return false;
    });

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

    if ($('.info').is(':empty')) {
        $('.info').hide();
    }

    if ($('#topbar').innerWidth() < 840) {
        document.fonts.ready.then(function () {
            centerMobileIcons();
        });
    }

    sticky_tables();

    post_popup();
});


window.syncColumnWidths = function () {
    $('.table-sticky table').each(function () {
        var $originalTable = $(this);
        stickyId = $originalTable.attr('sticky-table');
        console.log(stickyId);
        var $stickyTable = $('[sticky-header="' + stickyId + '"]');;

        if (!$originalTable.length || !$stickyTable.length) return;

        var $originalThs = $originalTable.find('thead tr:first-child th');
        var $clonedThs = $stickyTable.find('thead tr:first-child th');

        $stickyTable.width($originalTable.outerWidth());

        $originalThs.each(function (index) {
            var width = $(this).outerWidth();
            $clonedThs.eq(index).css({
                width: width,
                minWidth: width,
                maxWidth: width
            });
        });
    });
}

function sticky_tables() {
    $('table').each(function () {
      const table = $(this);

      if (table.hasClass('no_sticky')) return;
      if (table.hasClass('mob')) return;

      if (!table.parent().hasClass('table-sticky')) {
        table.wrap('<div class="table-sticky"></div>');
      }

    // assign random id
    var randomId = Math.random().toString(36).substr(2, 9);
    table.attr('sticky-table', randomId);

    // copy thead
    var $originalThead = table.find('thead');
    var $clonedThead = $originalThead.clone();

    var $stickyTable = $('<table>').attr('sticky-header', randomId).append($clonedThead);
    var $stickyContainer = $('<div>').addClass('sticky-header').append($stickyTable);
    table.parent().before($stickyContainer);

    $(window).on('resize load', window.syncColumnWidths);
    window.syncColumnWidths();

    // add simple bar
    const wrapper = table.parent('.table-sticky')[0];
    if (!wrapper.classList.contains('simplebar-initialized')) {
        new SimpleBar(wrapper, {
            autoHide: false
        });
    }


        /*
      table.find('tr').each(function () {
        $(this).find('th:first-child, td:first-child').addClass('sticky-col');
      });

      table.find('tr').each(function () {
        $(this).find('th:nth-child(2), td:nth-child(2)').addClass('sticky-col-2');
      });

      const corner = table.find('thead tr:first-child th:first-child');
      corner.addClass('sticky-header sticky-col');  */
    });
}

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
            if (res.k == 0) return;
            stop_spinner();

            uglipop({class:'popup', source:'html', content: res.v});

			reload_has_char();

            $('.popup').scrollTop( 0 );
            $(".popup .hide").hide();
        });

        return false;
    });
}

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

}


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


function jump_to(el) {
    const yOffset = -160;
    const y = el.getBoundingClientRect().top + window.pageYOffset + yOffset;
    window.scrollTo({top: y, behavior: 'smooth'});
}





function selectLanguage(lang) {
    xhttp.open("POST", set_language_url, true);
    xhttp.setRequestHeader("Content-type", "application/x-www-form-urlencoded");
    xhttp.send("language=" + lang);
}

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

function stripHTML(dirtyString) {
  var container = document.createElement('div');
  var text = document.createTextNode(dirtyString);
  container.appendChild(text);
  return container.innerHTML; // innerHTML will be a xss safe string
}

String.prototype.format = String.prototype.f = function() {
    var s = this,
        i = arguments.length;

    while (i--) {
        s = s.replace(new RegExp('\\{' + i + '\\}', 'gm'), arguments[i]);
    }
    return s;
};

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

function centerMobileIcons() {
    const $topbar = $('#topbar');
    const topbarWidth = $topbar.innerWidth();

    var $visibleElements = $topbar.find('.el');
    var elCount = 0;
    var totalElWidth = 0;

    $visibleElements.each(function () {
        var width = $(this).innerWidth();
        if (width > 0) {
            totalElWidth += width;
            elCount += 1;
        }
    });

    var totalSpacing = topbarWidth * 0.95 - totalElWidth;
    var margin = totalSpacing / elCount;

    $visibleElements.each(function (index) {
        var ml = margin / 2;

        $(this).closest('.el').css({
            'margin-left': `${ml}px`,
            'margin-right': `${ml}px`
        });
    });
}

});


//function download_csv(csv, filename) {
//    var csvFile;
//    var downloadLink;
//
//    // CSV FILE
//    csvFile = new Blob([csv], {type: "text/csv"});
//
//    // Download link
//    downloadLink = document.createElement("a");
//
//    // File name
//    downloadLink.download = filename;
//
//    // We have to create a link to the file
//    downloadLink.href = window.URL.createObjectURL(csvFile);
//
//    // Make sure that the link is not displayed
//    downloadLink.style.display = "none";
//
//    // Add the link to your DOM
//    document.body.appendChild(downloadLink);
//
//    // Lanzamos
//    downloadLink.click();
//}

//function export_table_to_csv(sel, filename) {
//    var csv = [];
//    var rows = document.querySelectorAll(sel + " tr");
//
//    for (var i = 0; i < rows.length; i++) {
//        var row = [], cols = rows[i].querySelectorAll("td, th");
//
//        for (var j = 0; j < cols.length; j++) {
//            var tx = cols[j].innerText;
//            tx = tx.replace(/\t/g, " ");
//            tx = tx.replace(/\n/g, " ");
//            tx = tx.replace(/\r/g, " ");
//            row.push(tx);
//        }
//
//        csv.push(row.join("\t"));
//    }
//
//    // Download CSV
//    download_csv(csv.join("\n"), filename);
//}

//function go_table_csv(eid) {
//    export_table_to_csv('#' + eid, "table " + document.title + ".csv");
//    return false;
//}

//function table_csv() {
//    $(".manage table").each(function( index ) {
//
//        if ( $(this).hasClass("no_csv") ) return;
//
//        if ( $(this).find('tbody').length === 0 || $(this).find('tbody tr').length === 0 ) {
//            return;
//        }
//
//        if ( $(this).is("#idSelector") ) {
//            var eid = $(this).attr('id');
//        } else {
//            var eid = "a" + Math.random().toString(36).slice(2);
//            $(this).attr('id', eid);
//        }
//
//        $(this).parent().after('<p class="go_table"><a href="#" eid="' + eid + '">Download as csv</a></p>');
//    });
//
//    $(".go_table a").on( "click", function() {
//        eid = $(this).attr("eid");
//        go_table_csv(eid);
//    });
//}
