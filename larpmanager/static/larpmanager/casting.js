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

var num_pref = window['num_pref'];
var choices = window['choices'];
var players = window['players'];
var chosen = window['chosen'];
var not_chosen = window['not_chosen'];
var preferences = window['preferences'];
var didnt_choose = window['didnt_choose'];
var nopes = window['nopes'];
var taken = window['taken'];
var mirrors = window['mirrors'];
var casting_avoid = window['casting_avoid'];
var avoids = window['avoids'];
var csrf_token = window['csrf_token'];
var tick = window['tick'];
var tipo = window['typ'];
var toggle_url = window['toggle_url'];

var trads = window['trads'];

var reg_priority = window['reg_priority'];
var pay_priority = window['pay_priority'];

    /*
$('form').submit(function() {
    var c = confirm("{% trans "Confermi l'assegnazione" %}?");
    return c; //you can just return c because it will be true or false
});   */

var disappoint = [1, 2, 4, 8, 16, 32, 64, 128, 256, 512];

var grid = '#main_grid';

function debug(data) {
    alert(JSON.stringify(data));
}

// First, checks if it isn't implemented yet.
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

function load_grid() {
    if (not_chosen.length > 0) {
        $('#not_chosen').append(trads['ne']);
        for (var ix = 0; ix < not_chosen.length; ix++) {
            $('#not_chosen').append(' / ' + choices[not_chosen[ix]]);
        }
    }

    if (didnt_choose.length > 0) {
        $('#didnt_choose').append(trads['ge']);
        for (var ix = 0; ix < didnt_choose.length; ix++) {
            $('#didnt_choose').append(' - ' + players[didnt_choose[ix]]['name']);
        }
        $('#didnt_choose').append(' - ' + trads['le'] + ': ');
        for (var ix = 0; ix < didnt_choose.length; ix++) {
            if (ix > 0) $('#didnt_choose').append(', ');
            $('#didnt_choose').append(players[didnt_choose[ix]]['email']);
        }
    }

    var order = {};

    for (key in preferences) {
        ord = players[key]['prior'] * 1000 + players[key]['reg_days'] + players[key]['pay_days'];
        order[key] = ord;
    }


    var keyValues = [];

    var mirrored = [];
    for (const [key, value] of Object.entries(mirrors)) {
        mirrored.push(parseInt(value));
    }
    mirrored.sort();
    // console.log(mirrored);

    for (var key in order) {
      keyValues.push([ key, order[key] ])
    }

    keyValues.sort(function compare(kv1, kv2) {
        return kv2[1] - kv1[1]
    })

    var aux = '<tr><th></th><th>{0}</th><th>{1}</th>'.format(trads['g'], trads['p']);
    if (casting_avoid)
        aux += '<th>{0}</th>'.format(trads['e'])
    for (var ix = 0; ix < num_pref; ix++) {
        aux += '<th>Pref {0}</th>'.format(ix+1);
    }
    aux += '</tr>'
    $(grid).append(aux);

    // console.log(keyValues);

    taken.sort();

    for (const el of keyValues) {
        // console.log(el);
        key = el[0];

        av = "";
        if (key in avoids) av = avoids[key];

        // console.log(key);
        aux = '<tr class="p_{1}"><td class="include"><input type=checkbox></td><td>{0}</td><td>{2}</td>'.format(players[key]['name'], key, players[key]['prior']);
        if (casting_avoid)
            aux += '<td>{0}</td>'.format(av)
        //~ console.log(num_pref);
        //~ console.log(preferences[key].length);
        for (var ix = 0; ix < Math.min(num_pref, preferences[key].length); ix++) {

            var k = preferences[key][ix];
            aux += '<td id="cost_{0}" class="mn"><select class="pref" disabled style="display:none;">'.format(ix);
            for (var iy = 0; iy < num_pref; iy++) {
                aux += ' <option value="{0}">{1}</option>'.format(iy, iy+1);
            }
            aux += ' <option value="99">NAN</option>';

            // disabilita automaticamente se il giocatore ha selezionato un'opzione non disponibile
            if (k == '' || !(parseInt(k) in choices))
                aux += '</select><br /><span class="dis EP">EP</span></td>';
            else if (mirrored.includes(parseInt(k))) {
                aux += '</select><br /><span class="dis MR">MR</span></td>';
            } else if (taken.includes(parseInt(k))) {
                aux += '</select><br /><span class="dis CH">CH</span></td>';
            } else {
                tgl = '<a class="dis change" pid="{0}" oid="{1}">YES</a>'.format(key, k);
                var nm_choice = 'EMPTY';
                if (k != '') nm_choice = choices[k];
                aux += '</select><br /><span class="c_{0}">{1}</span> - {2}</td>'.format(k, nm_choice, tgl);
            }
        }
        aux += '</tr>';
        $(grid).append(aux);

        select_option(key);
    }

    // update the preference order, and set automatic recalibration
    $('.change').click(function() {
        $( this ).toggleClass('NO');
        if ($( this ).hasClass('NO')) $( this ).text('NO'); else $( this ).text('YES');
        // debug(k);
        pid = $( this ).attr('pid');
        select_option(pid);
        oid = $( this ).attr('oid');
        data = {'pid': pid, 'oid': oid, csrfmiddlewaretoken: csrf_token };
        // console.log(data);
        $.post(toggle_url, data);
    });

    // load previous nopes
    for (pid in nopes) {
        // console.log(pid);
        ar = nopes[pid];
        for (var ix = 0; ix < ar.length; ix++) {
            oid = ar[ix];
            // console.log(oid);
            var el = $( "a.change[pid='{0}'][oid='{1}'".format(pid, oid) );
            el.toggleClass('NO');
            if (el.hasClass('NO')) el.text('NO'); else el.text('YES');
        }
        select_option(pid);
    }

    $('.tablesorter').tablesorter();
}

function select_option(pl) {
    var incr = 0;
    $('.p_{0} .mn'.format(pl)).each(function() {
        var vl = incr;
        if ($(this).find('.dis').hasClass('NO') || ($(this).find('.dis').hasClass('MR')) || ($(this).find('.dis').hasClass('CH')) || ($(this).find('.dis').hasClass('EP')))
            vl = 8;
        else
            incr++;

        // console.log(vl);

        $(this).find('.pref').val(vl);
    });
}

function exec_assigner() {

        var variab = {};

        var included = {};

        for (key in preferences) {
            var logg = false;

            if (logg) console.log(players[key]['name']);
            if (logg) console.log(players[key]['reg_days']);

            var include = false;

            $('.p_{0} .include input[type=checkbox]'.format(key)).each(function() {
               if ($(this).is(":checked")) {
                   include = true;
               }
            });
            if (logg) console.log(include);
            if (!include)
                continue;

            for (var ix = 0; ix < Math.min(num_pref, preferences[key].length); ix++) {
                var ch = preferences[key][ix];
                var id = 'p{0}_c{1}'.format(key, ch);
                if (logg) console.log(id);
                var iy = $('.p_{0} #cost_{1} .pref'.format(key, ix)).val();
                if (logg) console.log(iy);
                var dis = 99999;
                if (iy != null) {
                    dis = disappoint[iy];
                    dis *= (players[key]['reg_days'] * reg_priority / 30.0);
                    dis *= (players[key]['pay_days'] * pay_priority / 30.0);
                    var prior = players[key]['prior'];
                    dis *= prior;
                }

                v = {}
                v['disappoint'] = Math.floor(dis);
                v['p' + key] = '1';
                v['c' + ch] = '1';
                if (iy != null) v['o' + key] = '0'; else v['o' + key] = '1';

                variab[id] = v;

                if (logg) console.log(ch);
                if (logg) console.log(v);

                included[key] = 1;
            }
        }

        // debug(variab);

        var constr = {};

        // minimum 1 character for player
        for (key in included) {
            constr['p' + key] = {'min': 1};
            // console.log(key);
        }

        // no "impossible" choices for player
        for (key in included) {
            constr['o' + key] = {'max': 0};
        }

        // maximum 1 player for character
        for (key in choices) {
            constr['c' + key] = {'max': 1};
        }

        // console.log(constr);

        var model = {
            'optimize': 'disappoint',
            'opType': 'min',
            'variables': variab,
            'constraints': constr,
        }

        // console.log(variab);
        // console.log(constr);

        /*
        var model2 = {
            'optimize': 'capacity',
            'opType': 'max',
            'constraints': {
                'plane': {'max': 44},
                'person': {'max': 512},
                'cost': {'max': 300000}
            },
            'variables': {
                'brit': {
                    'capacity': 20000,
                    'plane': 1,
                    'person': 8,
                    'cost': 5000
                },
                'yank': {
                    'capacity': 30000,
                    'plane': 1,
                    'person': 16,
                    'cost': 9000
                }
            }
        } */

        var results = solver.Solve(model);
        // debug(results);
        // console.log(results);

        var counter = {};
        var tot = 0;
        var vl = '';
        for (var ix = 0; ix < num_pref; ix++) {
            counter[ix] = 0;
        }

        $('.sel').each(function() {
            $(this).removeClass('sel');
        });

        var ass = {};
        for (key in included) {
            for (var ix = 0; ix < Math.min(num_pref, preferences[key].length); ix++) {
                var ch = preferences[key][ix];
                var id = 'p{0}_c{1}'.format(key, ch);
                var el = $('.p_{0} .c_{1}'.format(key, ch));
                if (!(id in results)) continue;

                el.addClass('sel');
                counter[ix] += 1;
                tot += 1;
                vl += id + ' ' ;

                if (mirrors[ch] !== undefined) {
                    ass[parseInt(mirrors[ch])] = '{2} - {0} [-> {1}]'.format(players[key]['name'], choices[ch], choices[mirrors[ch]]);
                } else {
                    ass[parseInt(ch)] = '{1} - {0}'.format(players[key]['name'], choices[ch]);
                }

            }
        }

        $('#res').val(vl);

        $('#risultati').empty();
        var tx = ''; // disappoint globale: {0} <table><tr>'.format(results['result']);
        for (var ix = 0; ix < num_pref; ix++) {
            tx += '<th>{0}</th>'.format(ix + 1);
        }
        tx += '</tr><tr>';
        for (var ix = 0; ix < num_pref; ix++) {
            tx += '<td>{0}\%</td>'.format( (counter[ix] * 100.0 / tot).toFixed(1) );
        }
        tx += '</tr></table>';
        $('#risultati').append(tx);

        var sorted = sortObjectByKeys(ass);
        $('#assegnazioni').empty();
        tx = '';
        for (const [key, value] of Object.entries(sorted)) {
            tx += value + '<br />'
        }
        $('#assegnazioni').append(tx);

        $('#load').show();

        $('.tablesorter').tablesorter();

        if (!results['feasible']) {
            debug("WARNING - PROBLEM NOT FEASIBLE");
            $('#load').hide();
        } else
            $('#load').show();

    }

    $(function() {
        load_grid();

        var num_pl = Object.keys(players).length;
        $('#num_pl').html(num_pl);

        var num_ch = Object.keys(choices).length;
        $('#num_ch').html(num_ch);

        if (num_ch < num_pl) debug("WARNING - LESS CHARACTERS THAN PLAYERS. PROBLEM UNFEASIBLE");

        $('#load').hide();

        $('#exec').click(function() {
            try {
                exec_assigner();
            } catch (error) {
              console.error(error);
            }
            return false;
        });

        $('#fascia').change(function() {
            url = window['orga_casting_url'];
            url += this.value;
            window.location = url;
        });
        $('#fascia').val(tick);

        $('#tipo').change(function() {
            url = document.URL;
            url = url.replace(/&t=[0-9]/i, '');
            url += '&t=' + this.value;
            window.location = url;
        });
        $('#tipo').val(tipo);

        $('#load form').attr('action', document.URL);

        $('.include input[type=checkbox]').each(function() {
            $(this).prop('checked', true);
        });
    });

function sortObjectByKeys(o) {
    return Object.keys(o).sort().reduce((r, k) => (r[k] = o[k], r), {});
}
