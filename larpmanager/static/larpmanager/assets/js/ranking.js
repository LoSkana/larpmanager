/* Ranking drag-reorder widget */
(function ($) {
    'use strict';

    function initRanking($root) {
        var $list = $root.find('.ranking-list');
        var $hidden = $root.find('input[type="hidden"]');
        var maxRank = parseInt($root.data('max-rank'), 10) || 0;
        var $dragItem = null;
        var $lastDragTarget = null;

        // Number the ranked rows, flag the others, and store the ranked uuids in the hidden input
        function syncHiddenInput() {
            var uuids = [];
            $list.find('.ranking-item').each(function (index) {
                var ranked = maxRank === 0 || index < maxRank;
                $(this).toggleClass('ranking-unranked', !ranked);
                $(this).find('.ranking-position').text(ranked ? (index + 1) + '.' : '');
                if (ranked) uuids.push($(this).data('uuid'));
            });
            $hidden.val(uuids.join(','));
        }

        $list.on('dragstart', '.ranking-item', function () {
            $dragItem = $(this);
            setTimeout(function () {
                if ($dragItem) $dragItem.addClass('ranking-dragging');
            }, 0);
        });

        $list.on('dragover', '.ranking-item', function (e) {
            e.preventDefault();
            var $target = $(this);
            if (!$dragItem || $target.is($dragItem) || $target.is($lastDragTarget)) return false;
            $lastDragTarget = $target;
            var pos = $dragItem[0].compareDocumentPosition($target[0]);
            if (pos & Node.DOCUMENT_POSITION_FOLLOWING) {
                $dragItem.insertAfter($target);
            } else {
                $dragItem.insertBefore($target);
            }
            return false;
        });

        $list.on('dragend', '.ranking-item', function () {
            if ($dragItem) $dragItem.removeClass('ranking-dragging');
            $dragItem = null;
            $lastDragTarget = null;
            syncHiddenInput();
        });

        // Button fallback for touch devices, where native drag and drop is not available
        $list.on('click', '.ranking-up', function (e) {
            e.preventDefault();
            var $item = $(this).closest('.ranking-item');
            $item.insertBefore($item.prev('.ranking-item'));
            syncHiddenInput();
        });

        $list.on('click', '.ranking-down', function (e) {
            e.preventDefault();
            var $item = $(this).closest('.ranking-item');
            $item.insertAfter($item.next('.ranking-item'));
            syncHiddenInput();
        });

        syncHiddenInput();
    }

    window.addEventListener('DOMContentLoaded', function () {
        $('.ranking').each(function () { initRanking($(this)); });
    });

}(jQuery));
