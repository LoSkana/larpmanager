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

// ============================================================================
// GLOBAL VARIABLES - Data from Django backend
// ============================================================================

// Number of preference slots each player can select
var num_pref = window['num_pref'];

// Available character choices (id -> name mapping)
var choices = window['choices'];

// Player data (id -> {name, email, priority, reg_days, pay_days})
var players = window['players'];

// Characters that have been assigned
var chosen = window['chosen'];

// Characters that were not selected by any player
var not_chosen = window['not_chosen'];

// Player preferences (player_uuid -> [character_ids in preference order])
var preferences = window['preferences'];

// Players who didn't submit character preferences
var didnt_choose = window['didnt_choose'];

// Player choices that have been manually excluded (player_uuid -> [character_ids])
var nopes = window['nopes'];

// Characters already assigned/taken
var taken = window['taken'];

// Character mirror relationships (character_id -> mirrored_character_id)
var mirrors = window['mirrors'];

// Whether the avoid system is enabled
var casting_avoid = window['casting_avoid'];

// Players to avoid pairing (player_uuid -> avoid_list_string)
var avoids = window['avoids'];

// CSRF token for POST requests
var csrf_token = window['csrf_token'];

// Current tier/ticket ID being processed
var tick = window['tick'];

// Type of casting being performed
var tipo = window['typ'];

// URL endpoint for toggling character assignments
var toggle_url = window['toggle_url'];

// Translated UI strings
var trads = window['trads'];

// Priority multipliers for the optimization algorithm
var reg_priority = window['reg_priority'];  // Registration date priority weight
var pay_priority = window['pay_priority'];  // Payment date priority weight

// ============================================================================
// CONSTANTS AND UTILITY FUNCTIONS
// ============================================================================

/**
 * Disappointment scores for each preference level
 * Index 0 = first choice (score 1), Index 1 = second choice (score 2), etc.
 * Exponential scoring ensures getting lower preferences is significantly worse
 */
var disappoint = [1, 2, 4, 8, 16, 32, 64, 128, 256, 512];

// CSS selector for the main grid table
var grid = '#main_grid';

/**
 * Debug helper function - displays data as JSON alert
 * @param {*} data - Any data to display for debugging
 */
function debug(data) {
    alert(JSON.stringify(data));
}

/**
 * String format polyfill - adds Python-style string formatting to String prototype
 * Usage: "Hello {0}, you are {1} years old".format("John", 30)
 */
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

// ============================================================================
// GRID LOADING AND DISPLAY
// ============================================================================

/**
 * Loads and renders the casting grid table
 * Creates a table showing all players and their character preferences
 * Players are sorted by priority (player priority, registration date, payment date)
 */
function load_grid() {
    // Display characters that weren't selected by any player
    if (not_chosen.length > 0) {
        $('#not_chosen').append(trads['ne']);
        for (var ix = 0; ix < not_chosen.length; ix++) {
            $('#not_chosen').append(' / ' + choices[not_chosen[ix]]);
        }
    }

    // Display players who didn't submit preferences and their contact emails
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

    // Calculate sorting order for players
    // Formula: priority * 1000 + registration_days + payment_days
    // Higher score = higher priority in the list
    var order = {};

    for (key in preferences) {
        ord = players[key]['prior'] * 1000 + players[key]['reg_days'] + players[key]['pay_days'];
        order[key] = ord;
    }


    var keyValues = [];

    // Build list of mirrored character IDs (characters linked to other characters)
    var mirrored = [];
    for (const [key, value] of Object.entries(mirrors)) {
        mirrored.push(value);
    }
    mirrored.sort();

    // Convert order object to array of [player_uuid, priority_score] pairs for sorting
    for (var key in order) {
      keyValues.push([ key, order[key] ])
    }

    // Sort players by priority score (descending - highest priority first)
    keyValues.sort(function compare(kv1, kv2) {
        return kv2[1] - kv1[1]
    })

    // Build table header row
    var aux = '<tr><th></th><th>{0}</th><th>{1}</th>'.format(trads['g'], trads['p']);
    if (casting_avoid)
        aux += '<th>{0}</th>'.format(trads['e'])  // Add "Avoid" column if enabled
    for (var ix = 0; ix < num_pref; ix++) {
        aux += '<th>Pref {0}</th>'.format(ix+1);
    }
    aux += '</tr>'
    $(grid).append(aux);

    // Sort the taken characters list for easier lookup
    taken.sort();

    // Build table rows for each player (sorted by priority)
    for (const el of keyValues) {
        key = el[0];

        // Get avoid list for this player if it exists
        av = "";
        if (key in avoids) av = avoids[key];

        // Start building row: checkbox, player name, priority
        aux = '<tr class="p_{1}"><td class="include"><input type=checkbox></td><td>{0}</td><td>{2}</td>'.format(players[key]['name'], key, players[key]['prior']);
        if (casting_avoid)
            aux += '<td>{0}</td>'.format(av)  // Add avoid column if enabled

        // Build cells for each character preference
        for (var ix = 0; ix < Math.min(num_pref, preferences[key].length); ix++) {

            var k = preferences[key][ix];
            // Hidden select dropdown for preference ordering (used by algorithm)
            aux += '<td id="cost_{0}" class="mn"><select class="pref" disabled style="display:none;">'.format(ix);
            for (var iy = 0; iy < num_pref; iy++) {
                aux += ' <option value="{0}">{1}</option>'.format(iy, iy+1);
            }
            aux += ' <option value="99">NAN</option>';

            // Determine status of this preference and display accordingly
            if (k == '' || !(k in choices))
                // EP = Empty/Invalid choice
                aux += '</select><br /><span class="dis EP">EP</span></td>';
            else if (mirrored.includes(k)) {
                // MR = Mirrored character (linked to another character)
                aux += '</select><br /><span class="dis MR">MR</span></td>';
            } else if (taken.includes(k)) {
                // CH = Already chosen/taken by another player
                aux += '</select><br /><span class="dis CH">CH</span></td>';
            } else {
                // Available choice - show toggle button and character name
                tgl = '<a class="dis change" pid="{0}" oid="{1}">YES</a>'.format(key, k);
                var nm_choice = 'EMPTY';
                if (k != '') nm_choice = choices[k];
                aux += '</select><br /><span class="c_{0}">{1}</span> - {2}</td>'.format(k, nm_choice, tgl);
            }
        }
        aux += '</tr>';
        $(grid).append(aux);

        // Initialize preference ordering for this player
        select_option(key);
    }

    // Attach click handlers to YES/NO toggle buttons
    // When clicked, toggles between including/excluding a character choice
    $('.change').click(function() {
        $( this ).toggleClass('NO');
        if ($( this ).hasClass('NO')) $( this ).text('NO'); else $( this ).text('YES');

        // Recalculate preference ordering for this player
        pid = $( this ).attr('pid');
        select_option(pid);

        // Send toggle to server
        oid = $( this ).attr('oid');
        data = {'pid': pid, 'oid': oid, csrfmiddlewaretoken: csrf_token };
        $.post(toggle_url, data);
    });

    // Load previously saved "nope" choices (excluded character preferences)
    for (pid in nopes) {
        ar = nopes[pid];
        for (var ix = 0; ix < ar.length; ix++) {
            oid = ar[ix];
            // Find the toggle button and set it to NO
            var el = $( "a.change[pid='{0}'][oid='{1}'".format(pid, oid) );
            el.toggleClass('NO');
            if (el.hasClass('NO')) el.text('NO'); else el.text('YES');
        }
        // Recalculate preference ordering for this player
        select_option(pid);
    }

    // Initialize tablesorter plugin for sortable columns
    $('.tablesorter').tablesorter();
}

/**
 * Recalculates and updates the preference ordering values for a specific player
 * Assigns sequential preference numbers (0, 1, 2...) to available choices
 * Excluded or unavailable choices get value 8 (high disappointment)
 *
 * @param {string|number} pl - Player ID
 */
function select_option(pl) {
    var incr = 0;
    $('.p_{0} .mn'.format(pl)).each(function() {
        var vl = incr;
        // If choice is excluded (NO), mirrored (MR), taken (CH), or empty (EP), assign high value
        if ($(this).find('.dis').hasClass('NO') || ($(this).find('.dis').hasClass('MR')) || ($(this).find('.dis').hasClass('CH')) || ($(this).find('.dis').hasClass('EP')))
            vl = 8;  // High disappointment value = not usable
        else
            incr++;  // Sequential preference ordering

        // Update hidden select dropdown value (used by optimization algorithm)
        $(this).find('.pref').val(vl);
    });
}

// ============================================================================
// OPTIMIZATION ALGORITHM - Linear Programming Solver
// ============================================================================

/**
 * Executes the character assignment optimization algorithm
 * Uses linear programming to minimize total "disappointment" while satisfying constraints
 *
 * Algorithm overview:
 * 1. Build variables for each player-character pairing with disappointment scores
 * 2. Disappointment = base_score * registration_priority * payment_priority * player_priority
 * 3. Apply constraints: each player gets exactly 1 character, each character goes to max 1 player
 * 4. Solve using simplex algorithm to minimize total disappointment
 * 5. Display results and statistics
 */
function exec_assigner() {

        // Variables for the linear programming model (player-character pairings)
        var variab = {};

        // Track which players are included in optimization
        var included = {};

        // Build variables for each included player's preferences
        for (key in preferences) {
            var logg = false;  // Debug logging flag

            if (logg) console.log(players[key]['name']);
            if (logg) console.log(players[key]['reg_days']);

            // Check if this player is included (checkbox selected)
            var include = false;

            $('.p_{0} .include input[type=checkbox]'.format(key)).each(function() {
               if ($(this).is(":checked")) {
                   include = true;
               }
            });
            if (logg) console.log(include);
            if (!include)
                continue;  // Skip players not included in optimization

            // Process each preference for this player
            for (var ix = 0; ix < Math.min(num_pref, preferences[key].length); ix++) {
                var ch = preferences[key][ix];  // Character ID
                var id = 'p{0}_c{1}'.format(key, ch);  // Variable ID: "p123_c456"
                if (logg) console.log(id);

                // Get preference order value (0 = first choice, 1 = second, etc.)
                var iy = $('.p_{0} #cost_{1} .pref'.format(key, ix)).val();
                if (logg) console.log(iy);

                // Calculate disappointment score
                var dis = 99999;  // Default very high (impossible choice)
                if (iy != null) {
                    // Base disappointment from preference order (exponential: 1, 2, 4, 8, 16...)
                    dis = disappoint[iy];

                    // Multiply by registration date factor (earlier = higher disappointment)
                    dis *= (players[key]['reg_days'] * reg_priority / 30.0);

                    // Multiply by payment date factor (earlier = higher disappointment)
                    dis *= (players[key]['pay_days'] * pay_priority / 30.0);

                    // Multiply by player priority setting
                    var prior = players[key]['prior'];
                    dis *= prior;
                }

                // Build variable object for this player-character pairing
                v = {}
                v['disappoint'] = Math.floor(dis);  // Objective function: minimize this
                v['p' + key] = '1';  // Constraint: this uses 1 slot for player
                v['c' + ch] = '1';   // Constraint: this uses 1 slot for character
                if (iy != null) v['o' + key] = '0'; else v['o' + key] = '1';  // Constraint: valid vs invalid choice

                variab[id] = v;

                if (logg) console.log(ch);
                if (logg) console.log(v);

                included[key] = 1;
            }
        }

        // Build constraint set for the optimization problem
        var constr = {};

        // Constraint 1: Each player must get exactly 1 character (min: 1)
        for (key in included) {
            constr['p' + key] = {'min': 1};
        }

        // Constraint 2: No player can get an "impossible" choice (max: 0 invalid options)
        for (key in included) {
            constr['o' + key] = {'max': 0};
        }

        // Constraint 3: Each character can be assigned to at most 1 player (max: 1)
        for (key in choices) {
            constr['c' + key] = {'max': 1};
        }

        // Build the linear programming model
        var model = {
            'optimize': 'disappoint',  // Minimize total disappointment
            'opType': 'min',            // Minimization problem
            'variables': variab,        // All player-character pairings with scores
            'constraints': constr,      // Constraints defined above
        }

        // Solve the optimization problem using simplex algorithm
        var results = solver.Solve(model);
        // Process and display results

        // Counter for statistics: how many players got each preference level
        var counter = {};
        var tot = 0;  // Total assignments
        var vl = '';  // Space-separated list of assignments
        for (var ix = 0; ix < num_pref; ix++) {
            counter[ix] = 0;
        }

        // Clear previous selection highlighting
        $('.sel').each(function() {
            $(this).removeClass('sel');
        });

        // Build assignments from results
        var ass = {};  // Final assignments: character_id -> "Character - Player" string
        for (key in included) {
            for (var ix = 0; ix < Math.min(num_pref, preferences[key].length); ix++) {
                var ch = preferences[key][ix];
                var id = 'p{0}_c{1}'.format(key, ch);
                var el = $('.p_{0} .c_{1}'.format(key, ch));
                if (!(id in results)) continue;  // Skip if not selected by optimizer

                // Highlight selected choice in UI
                el.addClass('sel');
                counter[ix] += 1;  // Increment counter for this preference level
                tot += 1;
                vl += '{0}_{1}'.format(key, ch) + ' ' ;

                // Build assignment string (handle mirrored characters)
                if (mirrors[ch] !== undefined) {
                    ass[mirrors[ch]] = '{2} - {0} [-> {1}]'.format(players[key]['name'], choices[ch], choices[mirrors[ch]]);
                } else {
                    ass[ch] = '{1} - {0}'.format(players[key]['name'], choices[ch]);
                }

            }
        }

        // Store results in hidden field
        $('#res').val(vl);

        // Display statistics table (percentage of players who got each preference level)
        $('#risultati').empty();
        var tx = '<table><tr>';
        for (var ix = 0; ix < num_pref; ix++) {
            tx += '<th>{0}</th>'.format(ix + 1);
        }
        tx += '</tr><tr>';
        for (var ix = 0; ix < num_pref; ix++) {
            tx += '<td>{0}\%</td>'.format( (counter[ix] * 100.0 / tot).toFixed(1) );
        }
        tx += '</tr></table>';
        $('#risultati').append(tx);

        // Display assignment list (sorted by character ID)
        var sorted = sortObjectByKeys(ass);
        $('#assegnazioni').empty();
        tx = '';
        for (const [key, value] of Object.entries(sorted)) {
            tx += value + '<br />'
        }
        $('#assegnazioni').append(tx);

        // Show submit button
        $('#load').show();

        // Re-initialize tablesorter
        $('.tablesorter').tablesorter();

        // Check if solution is feasible (all constraints satisfied)
        if (!results['feasible']) {
            debug("WARNING - PROBLEM NOT FEASIBLE");
            $('#load').hide();
        } else
            $('#load').show();

    }

// ============================================================================
// INITIALIZATION AND EVENT HANDLERS
// ============================================================================

/**
 * Document ready handler - initializes the casting interface
 */
$(function() {
    // Load and display the player/character preference grid
    load_grid();

    // Display player and character counts
    var num_pl = Object.keys(players).length;
    $('#num_pl').html(num_pl);

    var num_ch = Object.keys(choices).length;
    $('#num_ch').html(num_ch);

    // Warn if problem is inherently unfeasible (more players than characters)
    if (num_ch < num_pl) debug("WARNING - LESS CHARACTERS THAN PLAYERS. PROBLEM UNFEASIBLE");

    // Hide submit button until optimization is run
    $('#load').hide();

    // Execute button - runs the optimization algorithm
    $('#exec').click(function() {
        try {
            exec_assigner();
        } catch (error) {
          console.error(error);
        }
        return false;
    });

    // Tier/ticket dropdown - reload page with selected tier
    $('#fascia').change(function() {
        url = window['orga_casting_url'];
        url += this.value;
        window.location = url;
    });
    $('#fascia').val(tick);

    // Type dropdown - reload page with selected type
    $('#tipo').change(function() {
        url = document.URL;
        url = url.replace(/&t=[0-9]/i, '');
        url += '&t=' + this.value;
        window.location = url;
    });
    $('#tipo').val(tipo);

    // Set form action to current URL (preserves query parameters)
    $('#load form').attr('action', document.URL);

    // Check all "include" checkboxes by default
    $('.include input[type=checkbox]').each(function() {
        $(this).prop('checked', true);
    });
});

/**
 * Sorts an object by its keys (numerical order)
 * @param {Object} o - Object to sort
 * @returns {Object} New object with keys in sorted order
 */
function sortObjectByKeys(o) {
    return Object.keys(o).sort().reduce((r, k) => (r[k] = o[k], r), {});
}
