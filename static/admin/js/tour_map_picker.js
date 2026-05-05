(function () {
  function parseNumber(value) {
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
  }

  function findField(container, suffix) {
    return container.querySelector('[name$="' + suffix + '"]');
  }

  function setFieldValue(field, value) {
    if (!field) return;
    field.value = value == null ? '' : String(value);
    field.dispatchEvent(new Event('change', { bubbles: true }));
  }

  function parseGoogleMapsInput(query) {
    const raw = (query || '').trim();
    if (!raw) return null;

    const coordMatch = raw.match(/@(-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?)/);
    if (!coordMatch) return null;

    const lat = parseNumber(coordMatch[1]);
    const lon = parseNumber(coordMatch[2]);
    if (lat == null || lon == null) return null;

    let name = '';
    const placeMatch = raw.match(/\/place\/([^/]+)/);
    if (placeMatch && placeMatch[1]) {
      name = decodeURIComponent(placeMatch[1].replace(/\+/g, ' '));
    }

    return {
      lat: String(lat),
      lon: String(lon),
      name: name || 'Pinned place',
      display_name: name || 'Pinned place from Google Maps',
      address: { country_code: 'ma' },
      _source: 'google_url',
    };
  }

  async function fetchSearch(query, restrictMorocco) {
    const params = new URLSearchParams({
      format: 'jsonv2',
      limit: '8',
      'accept-language': 'fr',
      q: query,
      addressdetails: '1',
    });
    if (restrictMorocco) {
      params.set('countrycodes', 'ma');
    }
    const url = 'https://nominatim.openstreetmap.org/search?' + params.toString();
    const response = await fetch(url, { headers: { Accept: 'application/json' } });
    if (!response.ok) throw new Error('Search failed');
    return response.json();
  }

  function dedupeResults(results) {
    const seen = new Set();
    return results.filter((result) => {
      const key = `${result.lat}|${result.lon}|${result.display_name || ''}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }

  function scoreResult(result, query) {
    const haystack = `${result.name || ''} ${result.display_name || ''}`.toLowerCase();
    const q = (query || '').toLowerCase();
    let score = 0;
    if ((result.address && result.address.country_code) === 'ma') score += 50;
    if (haystack.includes(q)) score += 30;
    q.split(/\s+/).filter(Boolean).forEach((token) => {
      if (haystack.includes(token)) score += 6;
    });
    return score;
  }

  async function searchPlaces(query, cityHint) {
    const googleCandidate = parseGoogleMapsInput(query);
    if (googleCandidate) {
      return [googleCandidate];
    }

    const queries = [
      query,
      cityHint ? `${query}, ${cityHint}, Morocco` : '',
      `${query}, Morocco`,
    ].filter(Boolean);

    const collected = [];
    for (const q of queries) {
      const restricted = await fetchSearch(q, true);
      collected.push(...restricted);
      if (!restricted.length) {
        const broader = await fetchSearch(q, false);
        collected.push(...broader);
      }
    }

    return dedupeResults(collected)
      .sort((a, b) => scoreResult(b, query) - scoreResult(a, query))
      .slice(0, 6);
  }

  function cityFromAddress(address) {
    if (!address) return '';
    return address.city || address.town || address.village || address.municipality || address.county || '';
  }

  function renderResults(resultsWrap, results, onPick) {
    if (!results.length) {
      resultsWrap.innerHTML = '<div class="tour-map-picker-empty">No place found in Morocco for this search.</div>';
      return;
    }

    resultsWrap.innerHTML = results.map((result, index) => {
      const name = (result.name || result.display_name || 'Place').replace(/</g, '&lt;');
      const subtitle = (result.display_name || '').replace(/</g, '&lt;');
      return `
        <button type="button" class="tour-map-result" data-index="${index}">
          <span class="tour-map-result-title">${name}</span>
          <span class="tour-map-result-subtitle">${subtitle}</span>
        </button>
      `;
    }).join('');

    resultsWrap.querySelectorAll('.tour-map-result').forEach((button) => {
      button.addEventListener('click', function () {
        const result = results[Number(button.dataset.index)];
        if (result) onPick(result);
      });
    });
  }

  function initPicker(container) {
    if (container.dataset.mapPickerReady === '1') return;

    const mapSearch = findField(container, '-map_search');
    const coordinates = findField(container, '-coordinates');
    const latitude = findField(container, '-latitude');
    const longitude = findField(container, '-longitude');
    const placeName = findField(container, '-place_name');
    const city = findField(container, '-city');

    if (!mapSearch || !coordinates || !latitude || !longitude) return;

    container.dataset.mapPickerReady = '1';

    const wrap = document.createElement('div');
    wrap.className = 'tour-map-picker-wrap';
    wrap.innerHTML =
      '<div class="tour-map-picker-toolbar">' +
      '<button type="button">Search place</button>' +
      '</div>' +
      '<div class="tour-map-picker-note">Search for a place in Morocco, then click the correct result to save it.</div>' +
      '<div class="tour-map-picker-results"></div>';

    mapSearch.closest('.form-row, .field-map_search, .form-group, div')?.after(wrap);

    const searchButton = wrap.querySelector('button');
    const resultsWrap = wrap.querySelector('.tour-map-picker-results');

    const applyResult = (result) => {
      const lat = parseNumber(result.lat);
      const lon = parseNumber(result.lon);
      if (lat == null || lon == null) return;

      setFieldValue(latitude, lat.toFixed(15));
      setFieldValue(longitude, lon.toFixed(15));
      setFieldValue(coordinates, lat.toFixed(15) + ', ' + lon.toFixed(15));

      const address = result.address || {};
      if (placeName) {
        setFieldValue(placeName, result.name || (result.display_name || '').split(',')[0] || '');
      }
      if (city) {
        setFieldValue(city, cityFromAddress(address));
      }
      if (mapSearch) {
        setFieldValue(mapSearch, result.display_name || result.name || '');
      }
    };

    async function runSearch() {
      const query = (mapSearch.value || '').trim();
      if (!query) return;
      resultsWrap.innerHTML = '<div class="tour-map-picker-empty">Searching...</div>';
      try {
        const results = await searchPlaces(query, city ? city.value.trim() : '');
        renderResults(resultsWrap, results, applyResult);
      } catch (error) {
        resultsWrap.innerHTML = '<div class="tour-map-picker-empty">Search unavailable right now.</div>';
      }
    }

    searchButton.addEventListener('click', runSearch);
    mapSearch.addEventListener('keydown', function (event) {
      if (event.key === 'Enter') {
        event.preventDefault();
        runSearch();
      }
    });
  }

  function boot() {
    document.querySelectorAll('.inline-related, .grp-dynamic-form, .has_original, .empty-form').forEach(initPicker);
  }

  document.addEventListener('DOMContentLoaded', function () {
    boot();
    const observer = new MutationObserver(function () {
      boot();
    });
    observer.observe(document.body, { childList: true, subtree: true });
  });
})();
