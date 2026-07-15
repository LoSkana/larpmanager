/* Faction preference drag-reorder widget */
(function ($) {
    'use strict';

    function initFactionPref($root) {
        var $list = $root.find('.faction-pref-list');
        var $hidden = $root.find('input[type="hidden"]');
        var $dragItem = null;
        var $lastDragTarget = null;

        function syncHiddenInput() {
            var uuids = $list.find('.faction-pref-item').map(function () {
                return $(this).data('uuid');
            }).get();
            $hidden.val(uuids.join(','));
        }

        $list.on('dragstart', '.faction-pref-item', function () {
            $dragItem = $(this);
            setTimeout(function () {
                if ($dragItem) $dragItem.addClass('faction-pref-dragging');
            }, 0);
        });

        $list.on('dragover', '.faction-pref-item', function (e) {
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

        $list.on('dragend', '.faction-pref-item', function () {
            if ($dragItem) $dragItem.removeClass('faction-pref-dragging');
            $dragItem = null;
            $lastDragTarget = null;
            syncHiddenInput();
        });
    }

    window.addEventListener('DOMContentLoaded', function () {
        $('.faction-pref').each(function () { initFactionPref($(this)); });
    });

}(jQuery));
