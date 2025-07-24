/*!
 * LarpManager - https://larpmanager.com
 * Copyright (C) 2025 Scanagatta Mauro
 *
 * This file is part of LarpManager and is dual-licensed:
 *
 * 1. Under the terms of the GNU Affero General Public License (AGPL) version 3,
 *    as published by the Free Software Foundation. You may use, modify, and
 *    distribute this file under those terms.
 *
 * 2. Under a commercial license, allowing use in closed-source or proprietary
 *    environments without the obligations of the AGPL.
 *
 * For more information or to purchase a commercial license, contact:
 * commercial@larpmanager.com
 *
 * SPDX-License-Identifier: AGPL-3.0-or-later OR Proprietary
 */

 function slugify(Text) {
  return Text.toLowerCase()
             .replace(/[^\w ]+/g, '')
             .replace(/ +/g, '-');
}

var facs = window['facs'];

var all = window['all'];

var blank = window['blank'];

var char_url = window['char_url'];

var prof_url = window['prof_url'];

var faction_url = window['faction_url'];

var cover = window['cover'];

var cover_orig = window['cover_orig'];

var show_char = window['show_char'];

var show_teaser = window['show_teaser'];

var filters = {}

var fields = window['fields'];

var questions = window['questions'];

var options = window['options'];

var searchable = window['searchable'];

function compile_field(typ) {
    var st = new Set();
    var lbl = [];

    for (const [num, nel] of Object.entries(all)) {
        let el = nel;
        if ("hide" in el && el.hide === true) continue;
        if (el === undefined) continue;
        var cnt = el[typ];
        if (cnt === undefined) continue;

        aux = cnt.split(',');
        for (const v of aux) {
            vn = v.trim();
            sl = slugify(vn);
            if (st.has(sl)) continue;
            st.add(sl);

            lbl.push(vn);
        }
    }

    lbl.sort();
    for (const cnt of lbl) {
        sl = slugify(cnt);
        if (sl.length == 0) continue;

        $('<a>',{
            text: cnt,
            href: '#',
            tog: sl,
            typ: typ,
            click: function(){ return select($(this));}
        }).appendTo('#' + typ);
    }
}

function select(el) {
    select_el(el);
    $('#search').trigger("input");
    return false;
}

function select_el(el) {
    typ = el.attr('typ');
    id = el.attr('tog');

    // ids
    sel = filters[typ]['sel'];
    nsel = filters[typ]['nsel'];

    // labels
    sel_l = filters[typ]['sel_l'];
    nsel_l = filters[typ]['nsel_l'];

    var lbl = el.text().trim();

    if (el.hasClass('sel')) {
        el.removeClass('sel');
        sel.delete(id);
        sel_l.delete(lbl);
        el.addClass('nsel');
        nsel.add(id);
        nsel_l.add(lbl);
    } else if (el.hasClass('nsel')) {
        el.removeClass('nsel');
        nsel.delete(id);
        nsel_l.delete(lbl);
    } else {
        el.addClass('sel');
        sel.add(id);
        sel_l.add(lbl);
    }

    // console.log(filters);
}

function check_atleatone(first, second) {
    for (const element of first) {
        if (second.has(element)) return true;
    }
    return false;
}

function check_selection(typ, st) {
    var included = filters[typ]['sel'].size == 0 || check_atleatone(st, filters[typ]['sel'])
    var excluded = filters[typ]['nsel'].size > 0 && check_atleatone(st, filters[typ]['nsel'])

    return included && !excluded;
}

function in_faction(el) {
    factions = new Set();
    for (var ix = 0; ix < el.factions.length; ix++) {
        factions.add(String(el.factions[ix]));
    }

    return check_selection('faction', factions)
}

function check_field(el, typ) {
    st = new Set();

    if (el) {
        var cnt = el[typ];
        if (cnt) {
            aux = cnt.split(',');
            for (const v of aux) {
                vn = v.trim();
                sl = slugify(vn);
                st.add(sl);
            }
        }
    }

    return check_selection(typ, st);
}

function in_fields(el) {
    var check = true;
    for (const [cf, value] of Object.entries(fields)) {
        check = check_field(el, cf) && check;
    }
    return check;
}

function check_custom_field(el, typ) {
    st = new Set();
    if (el['fields'] && el['fields'][typ]) {
        st = el['fields'][typ];
        st = st.map(num => String(num));
    }

    return check_selection('field_' + typ, st);
}

function in_custom_fields(el) {
    var check = true;
    for (const [cf, value] of Object.entries(searchable)) {
        check = check_custom_field(el, cf) && check;
    }
    return check;
}

function in_spec(el) {
    specs = new Set();

    if (el['player_id'] > 0) specs.add('pl');

    return check_selection('spec', specs)
}

function found(key, el) {
    for (var k in el) {
        if(el[k] === null && el[k] === '') continue;
        if (uniform(el[k]).includes(key)) return true;
    }

    return false;
}

function uniform(s) {
    if (s === '' || s === undefined || s === null ) return '';
    return s.toString().toLowerCase().trim();
}

function search(key) {
    key = uniform(key);
    var top = '';
    var characters = '';
    var first = true;
    var cnt = 0;

    if (!show_char) return;

    var res = [];
    for (const [num, el] of Object.entries(all)) {
        if ("hide" in el && el.hide === true) continue;
        if (found(key, el) && in_faction(el) && in_spec(el) && in_fields(el) && in_custom_fields(el)) res.push(el);
    }

    if (res.length > 0) {

        for (var ix = 0; ix < res.length; ix++) {
            var el = res[ix];
            var name = el['name'];
            if (el['title'].length > 0) name += " - {0}".format(el['title']);
            if (first) first = false; else { top += ", "; characters += '<hr class="clear" />'; }
            top += "<small style='display: inline-block'><a href='#num{0}'>{1}</a></small>".format(el['number'], name);

            var pf = blank;
            if (cover) {
                if (cover_orig && el['cover'])
                    pf = el['cover'];
                else if (el['thumb'])
                    pf = el['thumb'];
            }
            var player = window['texts']['abs'];
            if (el['player_id'] > 0) {
                player = '<a href="{0}">{1}</a>'.format(prof_url.replace("/0", "/"+el['player_id']),el['player'])
                if (el['player_prof'])
                    pf = el['player_prof'];
            };

            characters += '<div class="gallery single list" id="num{0}">'.format(el['number']);
            characters += '<div class="el"><div class="icon"><img src="{0}" /></div></div>'.format(pf);
            characters += '<div class="text"><h3><a href="{0}">{1}</a></h3>'.format(char_url.replace("/0", "/"+el['number']), name);
            characters += '<div class="go-inline"><b>{1}:</b> {0}</div>'.format(player, window['texts']['pl']);

            for (const [k, value] of Object.entries(questions)) {
                if (el['fields'][k]) {
                    var field = el['fields'][k];
                    if (Array.isArray(field)) {
                        field = field.map(id => options[id]['display']);
                        field = field.join(', ');
                    }
                    characters += '<div class="go-inline"><b>{0}:</b> {1}</div>'.format(value['display'], field);
                }
            }

            gr = "";
            if (el['factions'].length > 0) {
                for (j = 0; j < el['factions'].length; j++) {
                    var fnum = el['factions'][j];
                    var fac = facs[fnum];
                    if (fac.number == 0) continue;
                    if (fac.typ == 'g') continue;
                    if (j != 0) gr += ", ";
                    gr += '<a href="{0}">{1}</a></h3>'.format(faction_url.replace("/0", "/" + fac.number), fac.name);
                }

                if (gr) characters += '<div class="go-inline"><b>{1}:</b> {0}</div>'.format(gr, window['texts']['factions']);
            }

            if (show_teaser && el['teaser'].length > 0) {
                teaser = $('#teasers .' + el['id']).html();
                characters += '<div class="go-inline">{0}</div>'.format(teaser);
            }

            characters += '</div></div>';

            cnt += 1;
        }

    }
    $('#top').html(top);
    $('#characters').html(characters);
    $('.num').html(cnt);

    $('.incl').html(get_included_labels());
    $('.escl').html(get_escluded_labels());

    reload_has_char();
}

function get_included_labels() {

    var txt = [];
    var el = filters['faction']['sel_l'];
    if (el.size > 0) txt.push(window['texts']['factions'] + ": " + Array.from(el).join(', '));

    el = filters['spec']['sel_l'];
    if (el.size > 0) txt.push(window['texts']['specs'] + ": " + Array.from(el).join(', '));

    for (const [cf, value] of Object.entries(fields)) {
        el = filters[cf]['sel_l'];
        if (el.size > 0) txt.push(value + ': ' + Array.from(el).join(', '));
    }

    for (const [cf, value] of Object.entries(searchable)) {
        el = filters['field_' + cf]['sel_l'];
        if (el.size > 0) txt.push(questions[cf]['display'] + ': ' + Array.from(el).join(', '));
    }

    if (txt.length == 0)
        return window['texts']['all'];

    return txt.join(' - ');
}

function get_escluded_labels() {

    var txt = [];
    var el = filters['faction']['nsel_l'];
    if (el.size > 0) txt.push(window['texts']['factions'] + ": " + Array.from(el).join(', '));

    el = filters['spec']['nsel_l'];
    if (el.size > 0) txt.push(window['texts']['specs'] + ": " + Array.from(el).join(', '));

    for (const [cf, value] of Object.entries(fields)) {
        el = filters[cf]['nsel_l'];
        if (el.size > 0) txt.push(value + ': ' + Array.from(el).join(', '));
    }

    for (const [cf, value] of Object.entries(searchable)) {
        el = filters['field_' + cf]['nsel_l'];
        if (el.size > 0) txt.push(questions[cf]['display'] + ': ' + Array.from(el).join(', '));
    }

    if (txt.length == 0)
        return window['texts']['none'];

    return txt.join(' - ');
}

    $(document).ready(function(){
        fls = ['faction', 'spec'];

        $('#factions').find('a').each(function(e) {
            $(this).on("click", function() { return select($(this));});
        });

        $('#spec').find('a').each(function(e) {
            $(this).on("click", function() { return select($(this));});
        });

        for (const [k, value] of Object.entries(fields)) {
            compile_field(k);
            fls.push(k);
        }

        for (const [idq, options_id] of Object.entries(searchable)) {
            $('.custom_field_' + idq).find('a').each(function(e) {
                $(this).on("click", function() { return select($(this));});
            });
            fls.push('field_' + idq);
        }

        for (const typ of fls) {
            filters[typ] = {}
            for (const s of ['sel', 'nsel', 'sel_l', 'nsel_l']) {
                filters[typ][s] = new Set();
            }
        }
        search('');
        $('#search').on('input', function() { search($(this).val()); });
    });


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
