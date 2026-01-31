/*!
 * LarpManager - https://larpmanager.com
 * Copyright (C) 2025 Scanagatta Mauro
 *
 * This file is part of LarpManager and is dual-licensed:
 *
 * 1. Under the terms of the GNU Affero General Public License (AGPL) version 3,
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
// UTILITY FUNCTIONS
// ============================================================================

/**
 * Converts text to a URL-friendly slug
 * Converts to lowercase, removes special characters, replaces spaces with hyphens
 * @param {string} Text - Text to slugify
 * @returns {string} Slugified text
 */
function slugify(Text) {
  return Text.toLowerCase()
             .replace(/[^\w ]+/g, '')
             .replace(/ +/g, '-');
}

// ============================================================================
// GLOBAL VARIABLES - Data from Django backend
// ============================================================================

// Factions data (id -> {name, number, typ})
var facs = window['facs'];

// All characters data (id -> {name, title, player, factions, fields, etc.})
var all = window['all'];

// URL for blank profile image
var blank = window['blank'];

// URL template for character detail pages
var char_url = window['char_url'];

// URL template for player profile pages
var prof_url = window['prof_url'];

// URL template for faction pages
var faction_url = window['faction_url'];

// Whether to show cover images
var cover = window['cover'];

// Whether to show original cover images (vs thumbnails)
var cover_orig = window['cover_orig'];

// Whether to show character listings
var show_char = window['show_char'];

// Whether to show character teasers
var show_teaser = window['show_teaser'];

// Active filters state (populated on init)
// Structure: {filter_type: {sel: Set, nsel: Set, sel_l: Set, nsel_l: Set}}
var filters = {}

// Standard character fields to filter by
var fields = window['fields'];

// Custom form questions (id -> {name, ...})
var questions = window['questions'];

// Custom form options (id -> {name, ...})
var options = window['options'];

// Custom searchable fields (question_id -> [option_ids])
var searchable = window['searchable'];

// ============================================================================
// FILTER BUILDING AND MANAGEMENT
// ============================================================================

/**
 * Builds filter buttons for a specific field type by collecting all unique values
 * Creates clickable filter links for each unique value found in character data
 *
 * @param {string} typ - Field type to compile (matches character data property name)
 */
function compile_field(typ) {
    var st = new Set();  // Track unique slugified values (to avoid duplicates)
    var lbl = [];        // Store display labels in order

    // Collect all unique values for this field from character data
    for (const [num, nel] of Object.entries(all)) {
        let el = nel;
        if ("hide" in el && el.hide === true) continue;  // Skip hidden characters
        if (el === undefined) continue;
        var cnt = el[typ];
        if (cnt === undefined) continue;  // Skip if field not present

        // Field may contain comma-separated values
        aux = cnt.split(',');
        for (const v of aux) {
            vn = v.trim();
            sl = slugify(vn);
            if (st.has(sl)) continue;  // Skip if already added
            st.add(sl);

            lbl.push(vn);
        }
    }

    // Sort labels alphabetically and create filter buttons
    lbl.sort();
    for (const cnt of lbl) {
        sl = slugify(cnt);
        if (sl.length == 0) continue;

        // Create clickable filter link
        $('<a>',{
            text: cnt,
            href: '#',
            tog: sl,     // Slugified value for filtering
            typ: typ,    // Field type
            click: function(){ return select($(this));}
        }).appendTo('#' + typ);
    }
}

/**
 * Handles filter button click - cycles through three states and triggers search
 * @param {jQuery} el - The clicked filter element
 * @returns {boolean} false to prevent default link behavior
 */
function select(el) {
    select_el(el);
    $('#search').trigger("input");  // Re-run search with new filters
    return false;
}

/**
 * Cycles a filter button through three states:
 * 1. No class (neutral) -> 'sel' (include only this)
 * 2. 'sel' (include) -> 'nsel' (exclude this)
 * 3. 'nsel' (exclude) -> No class (neutral)
 *
 * @param {jQuery} el - The filter element to toggle
 */
function select_el(el) {
    typ = el.attr('typ');  // Filter type (faction, spec, custom field, etc.)
    id = el.attr('tog');   // Slugified value

    // Get filter sets for this type
    sel = filters[typ]['sel'];      // Selected (include) IDs
    nsel = filters[typ]['nsel'];    // Excluded IDs

    // Get filter label sets for this type
    sel_l = filters[typ]['sel_l'];    // Selected labels (for display)
    nsel_l = filters[typ]['nsel_l'];  // Excluded labels (for display)

    var lbl = el.text().trim();

    // Cycle through three states
    if (el.hasClass('sel')) {
        // State 1->2: Include -> Exclude
        el.removeClass('sel');
        sel.delete(id);
        sel_l.delete(lbl);
        el.addClass('nsel');
        nsel.add(id);
        nsel_l.add(lbl);
    } else if (el.hasClass('nsel')) {
        // State 2->3: Exclude -> Neutral
        el.removeClass('nsel');
        nsel.delete(id);
        nsel_l.delete(lbl);
    } else {
        // State 3->1: Neutral -> Include
        el.addClass('sel');
        sel.add(id);
        sel_l.add(lbl);
    }
}

// ============================================================================
// FILTER CHECKING LOGIC
// ============================================================================

/**
 * Checks if at least one element from first set is in second set
 * @param {Set} first - First set to check
 * @param {Set} second - Second set to check against
 * @returns {boolean} True if sets have at least one common element
 */
function check_atleatone(first, second) {
    for (const element of first) {
        if (second.has(element)) return true;
    }
    return false;
}

/**
 * Checks if a character passes the filter for a specific field type
 * Logic: Include if (no filters OR matches include filter) AND (not in exclude filter)
 *
 * @param {string} typ - Filter type to check
 * @param {Set} st - Set of values the character has for this field
 * @returns {boolean} True if character passes the filter
 */
function check_selection(typ, st) {
    // Include if no include filters set, or character has at least one included value
    var included = filters[typ]['sel'].size == 0 || check_atleatone(st, filters[typ]['sel'])

    // Exclude if exclude filters exist and character has at least one excluded value
    var excluded = filters[typ]['nsel'].size > 0 && check_atleatone(st, filters[typ]['nsel'])

    return included && !excluded;
}

/**
 * Checks if character passes faction filters
 * @param {Object} el - Character data object
 * @returns {boolean} True if character passes faction filters
 */
function in_faction(el) {
    factions = new Set();
    for (var ix = 0; ix < el.factions.length; ix++) {
        factions.add(String(el.factions[ix]));
    }

    return check_selection('faction', factions)
}

/**
 * Checks if character passes filter for a specific standard field
 * @param {Object} el - Character data object
 * @param {string} typ - Field type to check
 * @returns {boolean} True if character passes filter for this field
 */
function check_field(el, typ) {
    st = new Set();

    if (el) {
        var cnt = el[typ];
        if (cnt) {
            // Parse comma-separated values and slugify
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

/**
 * Checks if character passes ALL standard field filters
 * @param {Object} el - Character data object
 * @returns {boolean} True if character passes all field filters
 */
function in_fields(el) {
    var check = true;
    for (const [cf, value] of Object.entries(fields)) {
        check = check_field(el, cf) && check;
    }
    return check;
}

/**
 * Checks if character passes filter for a specific custom field (form question)
 * @param {Object} el - Character data object
 * @param {string} typ - Custom field question ID
 * @returns {boolean} True if character passes filter for this custom field
 */
function check_custom_field(el, typ) {
    st = new Set();
    if (el['fields'] && el['fields'][typ]) {
        st = el['fields'][typ];
        st = st.map(num => String(num));  // Convert to strings for comparison
    }

    return check_selection('field_' + typ, st);
}

/**
 * Checks if character passes ALL custom field filters
 * @param {Object} el - Character data object
 * @returns {boolean} True if character passes all custom field filters
 */
function in_custom_fields(el) {
    var check = true;
    for (const [cf, value] of Object.entries(searchable)) {
        check = check_custom_field(el, cf) && check;
    }
    return check;
}

/**
 * Checks if character passes special specification filters
 * Currently only checks if character has a player assigned
 * @param {Object} el - Character data object
 * @returns {boolean} True if character passes spec filters
 */
function in_spec(el) {
    specs = new Set();

    if (el['player_uuid'] && el['player_uuid'] !== null) specs.add('pl');  // 'pl' = has player

    return check_selection('spec', specs)
}

// ============================================================================
// SEARCH UTILITIES
// ============================================================================

/**
 * Checks if search key is found in any field of character data
 * @param {string} key - Normalized search string (lowercase, trimmed)
 * @param {Object} el - Character data object
 * @returns {boolean} True if key found in any field
 */
function found(key, el) {
    for (var k in el) {
        if(el[k] === null && el[k] === '') continue;
        if (uniform(el[k]).includes(key)) return true;
    }

    return false;
}

/**
 * Normalizes text for comparison (lowercase, trimmed)
 * @param {*} s - Text to normalize
 * @returns {string} Normalized text or empty string
 */
function uniform(s) {
    if (s === '' || s === undefined || s === null ) return '';
    return s.toString().toLowerCase().trim();
}

/**
 * Escapes HTML to prevent XSS attacks
 * @param {string} text - Text to escape
 * @returns {string} HTML-escaped text
 */
function escapeHtml(text) {
    var div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ============================================================================
// MAIN SEARCH FUNCTION
// ============================================================================

/**
 * Searches and displays characters matching the search query and active filters
 * Filters characters by:
 * - Text search (matches any field)
 * - Faction filters
 * - Special specs (has player, etc.)
 * - Standard field filters
 * - Custom field filters
 *
 * Displays results as character cards with:
 * - Character name and title
 * - Player assignment
 * - Profile image
 * - Faction memberships
 * - Custom field values
 * - Character teaser (if enabled)
 *
 * @param {string} key - Search text (will be normalized)
 */
function search(key) {
    key = uniform(key);  // Normalize search text
    var top = '';        // Quick navigation links at top
    var characters = ''; // Character cards HTML
    var first = true;    // Track first result for formatting
    var cnt = 0;         // Count matching characters

    if (!show_char) return;  // Exit if character display is disabled

    // Filter all characters by search text and active filters
    var res = [];
    for (const [num, el] of Object.entries(all)) {
        if ("hide" in el && el.hide === true) continue;  // Skip hidden characters
        // Check all filter conditions
        if (found(key, el) && in_faction(el) && in_spec(el) && in_fields(el) && in_custom_fields(el)) res.push(el);
    }

    if (res.length > 0) {

        // Build character cards for each result
        for (var ix = 0; ix < res.length; ix++) {
            var el = res[ix];
            var name = escapeHtml(el['name']);
            if (el['title'].length > 0) name += " - {0}".format(escapeHtml(el['title']));

            // Add to top navigation and separator
            if (first) first = false; else { top += ", "; characters += '<hr class="clear" />'; }
            top += "<small style='display: inline-block'><a href='#char{0}'>{1}</a></small>".format(el['uuid'], name);

            // Determine which profile image to use
            var pf = blank;  // Default to blank image
            if (cover) {
                if (cover_orig && el['cover'])
                    pf = el['cover'];  // Use original cover if available
                else if (el['thumb'])
                    pf = el['thumb'];  // Use thumbnail otherwise
            }

            // Build player assignment text and link
            var player = window['texts']['abs'];  // Default "absent" text
            if (el['player_uuid'] && el['player_uuid'] !== null) {
                player = '<a href="{0}">{1}</a>'.format(prof_url.replace("/0", "/"+el['player_uuid']), escapeHtml(el['player']))
                if (el['player_prof'])
                    pf = el['player_prof'];  // Use player's profile picture if assigned
            };

            // Build character card HTML
            characters += '<div class="gallery single list" id="char{0}">'.format(el['uuid']);
            characters += '<div class="el"><div class="icon"><img src="{0}" /></div></div>'.format(pf);
            characters += '<div class="text"><h3><a href="{0}">{1}</a></h3>'.format(char_url.replace("/0", "/"+el['uuid']), name);
            characters += '<div class="go-inline"><b>{1}:</b> {0}</div>'.format(player, window['texts']['pl']);

            // Add custom field values sorted by order
            // Convert questions object to array and sort by order field
            var sortedQuestions = Object.entries(questions).sort((a, b) => {
                return (a[1]['order'] || 0) - (b[1]['order'] || 0);
            });

            for (const [k, value] of sortedQuestions) {
                if (el['fields'][k]) {
                    var field = el['fields'][k];
                    if (Array.isArray(field)) {
                        // Multiple choice - join option names
                        field = field.map(id => escapeHtml(options[id]['name']));
                        field = field.join(' | ');
                    } else {
                        // Single value - escape HTML
                        field = escapeHtml(field);
                    }
                    characters += '<div class="go-inline"><b>{0}:</b> {1}</div>'.format(escapeHtml(value['name']), field);
                }
            }

            // Add faction memberships (excluding groups with typ='g')
            gr = "";
            if (el['factions'].length > 0) {
                for (j = 0; j < el['factions'].length; j++) {
                    var fnum = el['factions'][j];
                    var fac = facs[fnum];
                    if (fac.number == 0) continue;      // Skip faction 0
                    if (fac.typ == 'g') continue;       // Skip groups
                    if (j != 0) gr += ", ";
                    gr += '<a href="{0}">{1}</a></h3>'.format(faction_url.replace("/new", "/" + fac.uuid), escapeHtml(fac.name));
                }

                if (gr) characters += '<div class="go-inline"><b>{1}:</b> {0}</div>'.format(gr, window['texts']['factions']);
            }

            // Add character teaser if enabled
            if (show_teaser && el['teaser'].length > 0) {
                teaser = $('#teasers .' + el['uuid']).text();  // Get from hidden div, text only to prevent XSS
                characters += '<div class="go-inline">{0}</div>'.format(escapeHtml(teaser));
            }

            characters += '</div></div>';

            cnt += 1;
        }

    }

    // Update DOM with results
    $('#top').html(top);              // Quick navigation links
    $('#characters').html(characters); // Character cards
    $('.num').html(cnt);               // Result count

    // Update filter labels
    $('.incl').html(get_included_labels());
    $('.escl').html(get_escluded_labels());

    // Reload tooltip handlers for character cards
    reload_has_char();
}

/**
 * Generates human-readable text for active include filters
 * Shows which filters are currently set to "include"
 * @returns {string} Formatted text describing active include filters
 */
function get_included_labels() {

    var txt = [];

    // Add faction include filters
    var el = filters['faction']['sel_l'];
    if (el.size > 0) txt.push(window['texts']['factions'] + ": " + Array.from(el).map(escapeHtml).join(' | '));

    // Add spec include filters
    el = filters['spec']['sel_l'];
    if (el.size > 0) txt.push(window['texts']['specs'] + ": " + Array.from(el).map(escapeHtml).join(' | '));

    // Add standard field include filters
    for (const [cf, value] of Object.entries(fields)) {
        el = filters[cf]['sel_l'];
        if (el.size > 0) txt.push(escapeHtml(value) + ': ' + Array.from(el).map(escapeHtml).join(' | '));
    }

    // Add custom field include filters
    for (const [cf, value] of Object.entries(searchable)) {
        el = filters['field_' + cf]['sel_l'];
        if (el.size > 0) txt.push(escapeHtml(questions[cf]['name']) + ': ' + Array.from(el).map(escapeHtml).join(' | '));
    }

    if (txt.length == 0)
        return window['texts']['all'];  // Show "all" if no include filters

    return txt.join(' - ');
}

/**
 * Generates human-readable text for active exclude filters
 * Shows which filters are currently set to "exclude"
 * @returns {string} Formatted text describing active exclude filters
 */
function get_escluded_labels() {

    var txt = [];

    // Add faction exclude filters
    var el = filters['faction']['nsel_l'];
    if (el.size > 0) txt.push(window['texts']['factions'] + ": " + Array.from(el).map(escapeHtml).join(' | '));

    // Add spec exclude filters
    el = filters['spec']['nsel_l'];
    if (el.size > 0) txt.push(window['texts']['specs'] + ": " + Array.from(el).map(escapeHtml).join(' | '));

    // Add standard field exclude filters
    for (const [cf, value] of Object.entries(fields)) {
        el = filters[cf]['nsel_l'];
        if (el.size > 0) txt.push(escapeHtml(value) + ': ' + Array.from(el).map(escapeHtml).join(' | '));
    }

    // Add custom field exclude filters
    for (const [cf, value] of Object.entries(searchable)) {
        el = filters['field_' + cf]['nsel_l'];
        if (el.size > 0) txt.push(escapeHtml(questions[cf]['name']) + ': ' + Array.from(el).map(escapeHtml).join(' | '));
    }

    if (txt.length == 0)
        return window['texts']['none'];  // Show "none" if no exclude filters

    return txt.join(' - ');
}

// ============================================================================
// INITIALIZATION
// ============================================================================

/**
 * Document ready handler - initializes search interface
 * Sets up filter buttons, event handlers, and performs initial search
 */
$(document).ready(function(){
    fls = ['faction', 'spec'];  // List of filter types

    // Attach click handlers to faction filter links
    $('#factions').find('a').each(function(e) {
        $(this).on("click", function() { return select($(this));});
    });

    // Attach click handlers to spec filter links
    $('#spec').find('a').each(function(e) {
        $(this).on("click", function() { return select($(this));});
    });

    // Build filter buttons for standard fields
    for (const [k, value] of Object.entries(fields)) {
        compile_field(k);
        fls.push(k);
    }

    // Attach click handlers to custom field filter links
    for (const [idq, options_id] of Object.entries(searchable)) {
        $('.custom_field_' + idq).find('a').each(function(e) {
            $(this).on("click", function() { return select($(this));});
        });
        fls.push('field_' + idq);
    }

    // Initialize filter state objects for each filter type
    for (const typ of fls) {
        filters[typ] = {}
        for (const s of ['sel', 'nsel', 'sel_l', 'nsel_l']) {
            filters[typ][s] = new Set();
        }
    }

    // Perform initial search (empty = show all)
    search('');

    // Attach input handler to search box
    $('#search').on('input', function() { search($(this).val()); });
});

// ============================================================================
// TOOLTIP INITIALIZATION
// ============================================================================

/**
 * Initializes qTip tooltips for character cards
 * Must be called after character cards are added to DOM
 *
 * @param {string} parent - Optional parent selector to scope tooltip init
 */
function reload_has_char(parent='') {
    $(parent + ' ' + '.has_show_char').each(function() {
        $(this).qtip({
            content: {
                text: $(this).next('span')  // Content from next sibling span
            }, style: {
                classes: 'qtip-dark qtip-rounded qtip-shadow qtip-char'
            }, hide: {
                effect: function(offset) {
                    $(this).fadeOut(500);  // Fade out animation
                }
            }, show: {
                effect: function(offset) {
                    $(this).fadeIn(500);  // Fade in animation
                }
            }, position: {
                my: 'top left',
                at: 'bottom center',
            }
        });
    });

}
