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

$(document).ready(function() {

    $(".hide").hide();

    $('#banner h1').textfill({
    });

    $('#sidebar h1').textfill({
    });

    $('#header h1').textfill({
    });

    $("th label").each(function(index) {
        var txt = $( this ).text();
        $( this ).text(txt.replace(":", ""));
    });

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
            console.log(v);
            $(this).val(v);
        }
    });

    reload_has_char();

    reload_has_tooltip();

    $('.my_toggle').on( "click", function() {
        var k = $(this).attr("tog");
        var el =  $("." + k);
        el.toggle();
        // console.log(el.is(":visible"));
         if (el.is(":visible")) {
             var elements = document.getElementsByClassName(k);
             if (elements.length > 0)  {
                jump_to(elements[0]);
            }
            $(this).addClass('select');
        } else {
            $(this).removeClass('select');
        }
        return false;

    });

    table_csv();

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
        // alert(el.html());
        // console.log(el);

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

             // console.log(tx.toLowerCase());

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

});

function reload_has_char(parent='') {

    $(parent + ' ' + '.has_show_char').each(function() {

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
                my: 'top left',
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


function download_csv(csv, filename) {
    var csvFile;
    var downloadLink;

    // CSV FILE
    csvFile = new Blob([csv], {type: "text/csv"});

    // Download link
    downloadLink = document.createElement("a");

    // File name
    downloadLink.download = filename;

    // We have to create a link to the file
    downloadLink.href = window.URL.createObjectURL(csvFile);

    // Make sure that the link is not displayed
    downloadLink.style.display = "none";

    // Add the link to your DOM
    document.body.appendChild(downloadLink);

    // Lanzamos
    downloadLink.click();
}


function selectLanguage(lang) {
    xhttp.open("POST", set_language_url, true);
    xhttp.setRequestHeader("Content-type", "application/x-www-form-urlencoded");
    xhttp.send("language=" + lang);
}

function export_table_to_csv(sel, filename) {
    var csv = [];
    var rows = document.querySelectorAll(sel + " tr");

    for (var i = 0; i < rows.length; i++) {
        var row = [], cols = rows[i].querySelectorAll("td, th");

        for (var j = 0; j < cols.length; j++) {
            var tx = cols[j].innerText;
            tx = tx.replace(/\t/g, " ");
            tx = tx.replace(/\n/g, " ");
            tx = tx.replace(/\r/g, " ");
            row.push(tx);
        }

        csv.push(row.join("\t"));
    }

    // Download CSV
    download_csv(csv.join("\n"), filename);
}

function resize_fields() {
    $(".writing td").each(function( index ) {

        var textLength = stripHTML($(this).text()).length;

       $(this).find('.lm_tooltiptext').each(function () {
           textLength -=   stripHTML($(this).text()).length;
        });

       $(this).find('.popup_text').each(function () {
           textLength -=   stripHTML($(this).text()).length;
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

function table_csv() {
    $(".table_csv table").each(function( index ) {

        if ( $(this).hasClass("no_csv") ) return;

        if ( $(this).find('tbody').length === 0 || $(this).find('tbody tr').length === 0 ) {
            return;
        }

        if ( $(this).is("#idSelector") ) {
            var eid = $(this).attr('id');
        } else {
            var eid = "a" + Math.random().toString(36).slice(2);
            $(this).attr('id', eid);
        }

        $(this).after('<p class="go_table"><a href="#" eid="' + eid + '">Download as csv</a></p>');
    });

    $(".go_table a").on( "click", function() {
        eid = $(this).attr("eid");
        go_table_csv(eid);
    });
}

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

function go_table_csv(eid) {
    export_table_to_csv('#' + eid, "table " + document.title + ".csv");
    return false;
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

});
