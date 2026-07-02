/* Character dual-list widget (available / selected) */
(function ($) {
    'use strict';

    /* Parse "#123 Name" -> {num: "123", name: "Name"} */
    function parseLabel(label) {
        var m = label.match(/^#(\S+)\s+(.*)/);
        if (m) return {num: m[1], name: m[2]};
        return {num: '', name: label};
    }

    function makeCard(uuid, label, isSelected, pk) {
        var p = parseLabel(label);
        var icon = isSelected ? 'fa-times' : 'fa-plus';
        var $li = $('<li></li>')
            .attr('data-uuid', uuid)
            .attr('data-label', label)
            .attr('data-pk', pk || '')
            .addClass('char-dual-item')
            .append($('<span class="char-dual-icon"><i class="fa ' + icon + '"></i></span>'));
        if (p.num) {
            $li.append($('<span class="char-dual-num">' + $('<s>').text(p.num).html() + '</span>'));
        }
        $li.append($('<span class="char-dual-name">' + $('<s>').text(p.name).html() + '</span>'));
        return $li;
    }

    function initCharDual($root) {
        var searchUrl = $root.data('search-url');
        var $avList = $root.find('.char-dual-avail-list');
        var $selList = $root.find('.char-dual-sel-list');
        var $selSearch = $root.find('.char-dual-sel-search');
        var $count = $root.find('.char-dual-count');
        var $select = $root.find('select');
        var $avSearch = $root.find('.char-dual-available .char-dual-search');
        var debounceTimer = null;
        var csrfToken = $('meta[name="csrf-token"]').attr('content');

        /* Fill pre-rendered selected items (server-side initial load) */
        $selList.find('li[data-uuid]').each(function () {
            var $li = $(this);
            var uuid = $li.data('uuid');
            var label = $li.data('label');
            var pk = $li.data('pk');
            if (pk) {
                $select.find('option[value="' + uuid + '"]').attr('data-pk', pk);
            }
            $li.replaceWith(makeCard(uuid, label, true, pk));
        });

        function getSelectedUuids() {
            return $select.find('option').map(function () { return $(this).val(); }).get();
        }

        function updateCount() {
            $count.text($select.find('option').length);
        }

        function insertSorted($li) {
            var label = $li.data('label').toLowerCase();
            var $items = $selList.find('li');
            var inserted = false;
            $items.each(function () {
                if ($(this).data('label').toLowerCase() > label) {
                    $(this).before($li);
                    inserted = true;
                    return false;
                }
            });
            if (!inserted) {
                $selList.append($li);
            }
        }

        function addCharacter(uuid, label, pk) {
            if ($select.find('option[value="' + uuid + '"]').length) return;
            var $opt = $('<option selected></option>').val(uuid).text(label);
            if (pk) $opt.attr('data-pk', pk);
            $select.append($opt);
            insertSorted(makeCard(uuid, label, true, pk));
            updateCount();
            filterSelected($selSearch.val());
            $select.trigger('change');
        }

        function removeCharacter(uuid) {
            $select.find('option[value="' + uuid + '"]').remove();
            $selList.find('li[data-uuid="' + uuid + '"]').remove();
            updateCount();
            $select.trigger('change');
        }

        function filterSelected(term) {
            var q = (term || '').toLowerCase();
            $selList.find('li').each(function () {
                var match = !q || $(this).data('label').toLowerCase().indexOf(q) !== -1;
                $(this).toggle(match);
            });
        }

        function fetchAvailable(term) {
            var exclude = getSelectedUuids().join(',');
            $.ajax({
                url: searchUrl,
                method: 'POST',
                data: { term: term, exclude: exclude, csrfmiddlewaretoken: csrfToken },
                success: function (data) {
                    $avList.empty();
                    (data.res || []).forEach(function (item) {
                        $avList.append(makeCard(item[0], item[1], false, item[2]));
                    });
                }
            });
        }

        /* initial fetch */
        fetchAvailable('');

        /* available search */
        $avSearch.on('input', function () {
            clearTimeout(debounceTimer);
            var term = $(this).val();
            debounceTimer = setTimeout(function () { fetchAvailable(term); }, 300);
        });

        /* click available -> add */
        $avList.on('click', 'li', function () {
            addCharacter($(this).data('uuid'), $(this).data('label'), $(this).data('pk'));
            fetchAvailable($avSearch.val());
        });

        /* selected filter */
        $selSearch.on('input', function () { filterSelected($(this).val()); });

        /* click selected -> remove */
        $selList.on('click', 'li', function () {
            removeCharacter($(this).data('uuid'));
            fetchAvailable($avSearch.val());
        });

        updateCount();
    }

    window.addEventListener('DOMContentLoaded', function () {
        $('.char-dual').each(function () { initCharDual($(this)); });
    });

}(jQuery));
