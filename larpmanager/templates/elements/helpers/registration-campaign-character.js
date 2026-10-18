<script>
window.addEventListener('DOMContentLoaded', function() {

    $(function() {

        var member = $('#id_member');
        var select = $('#id_campaign_character');
        if (!member.length || !select.length) return;

        var noneOption = select.find('option[value=""]').clone();

        function loadCampaignCharacters() {
            select.empty().append(noneOption.clone());
            if (!member.val()) return;

            $.ajax({
                url: "{% url 'orga_registration_campaign_characters' run.get_slug %}",
                method: "POST",
                data: { mid: member.val() },
                headers: { 'X-CSRFToken': $('meta[name="csrf-token"]').attr('content') },
                datatype: "json",
            }).done(function(res) {
                if (res.k == 0) return;
                res.v.forEach(function(character) {
                    select.append($('<option>').val(character.uuid).text(character.name));
                });
                // preselect the most recently played character
                if (res.v.length) select.val(res.v[0].uuid);
            });
        }

        member.on('change', loadCampaignCharacters);
        loadCampaignCharacters();
    });
});
</script>
