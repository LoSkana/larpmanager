{% load i18n %}

<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>

<script>
window.addEventListener('DOMContentLoaded', function () {
    var latField = document.getElementById('id_pub_lat');
    var lonField = document.getElementById('id_pub_lon');
    if (!latField || !lonField) return;

    // Build map container and insert it before the form
    var mapWrapper = document.createElement('div');
    mapWrapper.innerHTML =
        '<div class="auto_resize"><div id="leaflet-search-row" style="display:flex;gap:6px;margin-bottom:6px;">' +
        '<input id="leaflet-search-input" type="text" style="flex:1;padding:4px 8px;" placeholder="{% filter escapejs %}{% trans "Search location..." %}{% endfilter %}" />' +
        '<button type="button" id="leaflet-search-btn">{% filter escapejs %}{% trans "Search" %}{% endfilter %}</button>' +
        '</div>' +
        '<div id="leaflet-map" style="height:350px;width:100%;border:1px solid #ccc;border-radius:4px;margin-bottom:16px;"></div></div>';

    var mainForm = document.getElementById('main_form');
    mainForm.parentNode.insertBefore(mapWrapper, mainForm);

    var map = L.map('leaflet-map').setView([0, 0], 5);

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
    }).addTo(map);

    var marker = null;

    function placeMarker(lat, lon, zoom, address) {
        var latlng = [lat, lon];
        if (marker) {
            marker.setLatLng(latlng);
        } else {
            marker = L.marker(latlng, { draggable: true }).addTo(map);
            marker.on('dragend', function () {
                var pos = marker.getLatLng();
                latField.value = pos.lat.toFixed(6);
                lonField.value = pos.lng.toFixed(6);
                reverseGeocode(pos.lat, pos.lng).then(function (result) {
                    if (result) fillAddress(result.address);
                });
            });
        }
        if (zoom) {
            map.setView(latlng, zoom);
        } else {
            map.panTo(latlng);
        }
        latField.value = lat.toFixed(6);
        lonField.value = lon.toFixed(6);
        if (address) {
            fillAddress(address);
        }
    }

    var placeField = document.getElementById('id_pub_place');
    var countryField = document.getElementById('id_pub_country');

    function fillAddress(address) {
        if (!address) return;
        var city = address.city || address.town || address.village || address.municipality || address.county || '';
        if (placeField && city) placeField.value = city;
        if (countryField && address.country) countryField.value = address.country;
    }

    function nominatim(params) {
        var qs = Object.keys(params).map(function(k) {
            return encodeURIComponent(k) + '=' + encodeURIComponent(params[k]);
        }).join('&');
        return fetch('https://nominatim.openstreetmap.org/search?format=json&limit=1&addressdetails=1&' + qs)
            .then(function (r) { return r.json(); })
            .then(function (data) { return (data && data.length > 0) ? data[0] : null; });
    }

    function reverseGeocode(lat, lon) {
        return fetch('https://nominatim.openstreetmap.org/reverse?format=json&addressdetails=1&lat=' + lat + '&lon=' + lon)
            .then(function (r) { return r.json(); })
            .then(function (data) { return data || null; });
    }

    // Initialize map position
    var initialLat = parseFloat(latField.value);
    var initialLon = parseFloat(lonField.value);

    if (!isNaN(initialLat) && !isNaN(initialLon)) {
        placeMarker(initialLat, initialLon, 13);
    } else {
        var where = '{{ form.instance.where|escapejs }}';
        var nationality = '{{ form.instance.association.nationality|escapejs }}' || 'it';
        var geocodePromise = where
            ? nominatim({ q: where })
            : nominatim({ country: nationality });
        geocodePromise.then(function (result) {
            if (result) {
                map.setView([parseFloat(result.lat), parseFloat(result.lon)], where ? 10 : 6);
            }
        });
    }

    // Click on map to place/move marker
    map.on('click', function (e) {
        reverseGeocode(e.latlng.lat, e.latlng.lng).then(function (result) {
            placeMarker(e.latlng.lat, e.latlng.lng, null, result ? result.address : null);
        });
    });

    // Search
    function doSearch() {
        var q = document.getElementById('leaflet-search-input').value.trim();
        if (!q) return;
        nominatim({ q: q }).then(function (result) {
            if (result) {
                placeMarker(parseFloat(result.lat), parseFloat(result.lon), 12, result.address);
            }
        });
    }

    document.getElementById('leaflet-search-btn').addEventListener('click', doSearch);
    document.getElementById('leaflet-search-input').addEventListener('keydown', function (e) {
        if (e.key === 'Enter') { e.preventDefault(); doSearch(); }
    });

    // Force Leaflet to recalculate size after insertion
    setTimeout(function () { map.invalidateSize(); }, 100);
});
</script>
