(function () {
  if (!window.L) return;
  const mapNode = document.getElementById('farm-map');
  const borderNode = document.getElementById('iran-border');
  const latInput = document.getElementById('id_farm_latitude');
  const lngInput = document.getElementById('id_farm_longitude');
  if (!mapNode || !borderNode || !latInput || !lngInput) return;

  const status = document.getElementById('map-status');
  const clearBtn = document.getElementById('map-clear');
  const locateBtn = document.getElementById('map-locate');
  const citySelect = document.getElementById('id_farm_city');
  const centersNode = document.getElementById('city-centers');
  const centers = centersNode ? JSON.parse(centersNode.textContent) : {};
  const border = JSON.parse(borderNode.textContent);
  const bounds = L.latLngBounds([border.south, border.west], [border.north, border.east]);
  const fa = (value) => String(value).replace(/\d/g, (digit) => '۰۱۲۳۴۵۶۷۸۹'[digit]);
  const iran = [32.5, 53.7];

  function inIran(lat, lng) {
    return border.polygons.some((ring) => {
      let inside = false;
      let previous = ring[ring.length - 1];
      for (const point of ring) {
        const [lngA, latA] = previous;
        const [lngB, latB] = point;
        if ((latA > lat) !== (latB > lat) && lng < ((lngB - lngA) * (lat - latA)) / (latB - latA) + lngA) {
          inside = !inside;
        }
        previous = point;
      }
      return inside;
    });
  }

  const hasPin = latInput.value !== '' && lngInput.value !== '';
  const selectedCenter = citySelect ? centers[citySelect.value] : null;
  const start = hasPin
    ? [parseFloat(latInput.value), parseFloat(lngInput.value)]
    : (selectedCenter ? [selectedCenter.lat, selectedCenter.lng] : iran);
  const zoom = hasPin ? 14 : (selectedCenter ? 11 : 6);
  const map = L.map(mapNode, {
    scrollWheelZoom: true,
    maxZoom: 20,
    maxBounds: bounds,
    maxBoundsViscosity: 1,
  });
  window.farmMap = map;
  L.tileLayer('https://{s}.google.com/vt/lyrs=y&hl=fa&x={x}&y={y}&z={z}', {
    maxZoom: 20,
    subdomains: ['mt0', 'mt1', 'mt2', 'mt3'],
    attribution: 'تصویر ماهواره‌ای &copy; Google',
  }).addTo(map);
  const icon = L.divIcon({
    className: 'farm-pin',
    html: '<span></span>',
    iconSize: [28, 28],
    iconAnchor: [14, 14],
  });
  let marker = null;

  function lockToIran() {
    map.invalidateSize();
    if (!map.getSize().x || !map.getSize().y) return;
    const minZoom = map.getBoundsZoom(bounds, true);
    if (Number.isFinite(minZoom)) map.setMinZoom(minZoom);
  }
  map.lockToIran = lockToIran;

  function setStatus(lat, lng) {
    if (!status) return;
    if (lat == null) {
      status.textContent = 'موقعیتی انتخاب نشده. این بخش اجباری نیست.';
      if (clearBtn) clearBtn.classList.add('hidden');
      return;
    }
    status.textContent = 'عرض ' + fa(lat.toFixed(5)) + ' · طول ' + fa(lng.toFixed(5));
    if (clearBtn) clearBtn.classList.remove('hidden');
  }

  function rejectOutside() {
    if (status) status.textContent = 'این نقطه خارج از مرز ایران است. جای دیگری از تصویر را انتخاب کنید.';
  }

  function write(lat, lng) {
    latInput.value = lat.toFixed(6);
    lngInput.value = lng.toFixed(6);
    setStatus(lat, lng);
  }

  function place(lat, lng, pan) {
    if (!inIran(lat, lng)) {
      rejectOutside();
      return;
    }
    if (!marker) {
      marker = L.marker([lat, lng], { draggable: true, icon }).addTo(map);
      marker.on('dragend', () => {
        const point = marker.getLatLng();
        if (!inIran(point.lat, point.lng)) {
          const savedLat = parseFloat(latInput.value);
          const savedLng = parseFloat(lngInput.value);
          if (Number.isFinite(savedLat) && Number.isFinite(savedLng)) marker.setLatLng([savedLat, savedLng]);
          if (status) status.textContent = 'نشانگر باید داخل مرز ایران بماند.';
          return;
        }
        write(point.lat, point.lng);
      });
    } else {
      marker.setLatLng([lat, lng]);
    }
    write(lat, lng);
    if (pan) map.setView([lat, lng], Math.max(map.getZoom(), 13));
  }

  let correcting = false;
  let lastInside = L.latLng(iran[0], iran[1]);
  map.on('moveend', () => {
    if (correcting) return;
    const center = map.getCenter();
    if (inIran(center.lat, center.lng)) {
      lastInside = center;
      return;
    }
    correcting = true;
    map.panTo(lastInside, { animate: false });
    correcting = false;
  });

  map.on('click', (event) => place(event.latlng.lat, event.latlng.lng, false));
  map.setView(start, zoom);
  if (hasPin && inIran(start[0], start[1])) place(start[0], start[1], false);
  else setStatus(null, null);

  if (clearBtn) {
    clearBtn.addEventListener('click', () => {
      if (marker) {
        map.removeLayer(marker);
        marker = null;
      }
      latInput.value = '';
      lngInput.value = '';
      setStatus(null, null);
    });
  }

  if (locateBtn) {
    locateBtn.addEventListener('click', () => {
      if (!navigator.geolocation) {
        if (status) status.textContent = 'مرورگر موقعیت مکانی را پشتیبانی نمی‌کند. روی تصویر ماهواره‌ای کلیک کنید.';
        return;
      }
      if (status) status.textContent = 'در حال دریافت موقعیت...';
      navigator.geolocation.getCurrentPosition(
        (position) => place(position.coords.latitude, position.coords.longitude, true),
        () => {
          if (status) status.textContent = 'دسترسی به موقعیت مرورگر ممکن نشد. روی تصویر ماهواره‌ای کلیک کنید.';
        }
      );
    });
  }

  if (citySelect) {
    citySelect.addEventListener('change', () => {
      if (marker) return;
      const center = centers[citySelect.value];
      if (center) map.setView([center.lat, center.lng], 11);
    });
  }

  setTimeout(lockToIran, 150);
})();
