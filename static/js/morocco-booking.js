/* A single shared guide calendar, checked again by the server when saving. */
document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('booking-form');
  if (!form?.dataset.availabilityUrl) return;
  const start = form.querySelector('[name="start_date"]');
  const end = form.querySelector('[name="end_date"]');
  const persons = form.querySelector('[name="persons"]');
  const button = document.getElementById('confirmCashBtn');
  const status = document.getElementById('guide-availability-status');
  const total = document.getElementById('live-price');
  const days = document.getElementById('live-days');
  const list = document.getElementById('guide-blocked-dates');
  const extras = [...document.querySelectorAll('.extra-activity-toggle')];
  const today = new Date();
  const isoToday = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
  const base = Number(document.getElementById('base-price').value);
  let blocked = JSON.parse(document.getElementById('guide-disabled-ranges').textContent);
  let timer, revision = 0, submitting = false, picker;

  const timestamp = value => /^\d{4}-\d{2}-\d{2}$/.test(value) ? Date.parse(`${value}T00:00:00Z`) : NaN;
  const nights = () => (timestamp(end.value) - timestamp(start.value)) / 86400000;
  const selection = () => new URLSearchParams(new FormData(form)).toString();
  function message(text, state = '') {
    status.textContent = text;
    status.dataset.state = state;
  }
  function renderBlocked() {
    list.replaceChildren();
    const ranges = blocked.filter(range => range.to >= isoToday);
    for (const range of ranges) {
      const item = document.createElement('li');
      item.textContent = `${range.from} – ${range.to} (inclusive)`;
      list.append(item);
    }
    if (!ranges.length) {
      const item = document.createElement('li');
      item.textContent = 'No dates currently blocked. Availability is checked again when you submit.';
      list.append(item);
    }
  }
  function localError() {
    if (!start.value || !end.value) return 'Choose your start and end dates.';
    const count = nights();
    if (!Number.isFinite(count) || count < 1) return 'End date must be after start date.';
    if (start.value < isoToday) return 'Choose a start date today or later.';
    if (count > 5) return 'Maximum allowed duration is 5 nights. Please choose a shorter date range.';
    if (!Number.isInteger(Number(persons.value)) || Number(persons.value) < 1) return 'Enter at least one traveler.';
    return '';
  }
  function price() {
    const count = nights(), travelers = Number(persons.value);
    if (localError()) {
      total.textContent = '—';
      days.textContent = '—';
      return;
    }
    let amount = base * count * travelers;
    extras.filter(el => el.checked).forEach(el => {
      amount += Number(el.dataset.price || 0) * travelers * (el.dataset.perNight === '1' ? count : 1);
    });
    if (travelers >= 5) amount *= .9;
    total.textContent = `${amount.toFixed(2)} $`;
    days.textContent = `${count} ${count === 1 ? 'night' : 'nights'}`;
  }
  async function check() {
    const current = ++revision;
    button.disabled = true;
    const error = localError();
    if (error) { message(error); return false; }
    message('Checking your guide’s calendar…');
    const url = new URL(form.dataset.availabilityUrl, location.origin);
    url.searchParams.set('start_date', start.value);
    url.searchParams.set('end_date', end.value);
    try {
      const response = await fetch(url, { cache: 'no-store', headers: { Accept: 'application/json' } });
      const data = await response.json();
      if (current !== revision) return false;
      if (!response.ok) throw new Error(data.error || 'Availability could not be checked. Please try again.');
      blocked = data.blocked_ranges;
      renderBlocked();
      if (picker) picker.setOptions({ lockDays: blocked.map(range => [range.from, range.to]) });
      message(data.message, data.available ? 'available' : 'error');
      button.disabled = !data.available;
      return data.available;
    } catch (error) {
      if (current !== revision) return false;
      message(error.message === 'Failed to fetch' ? 'Connection interrupted. Change your dates or reload to check again.' : error.message, 'error');
      return false;
    }
  }
  function changed() {
    revision++;
    clearTimeout(timer);
    button.disabled = true;
    price();
    const error = localError();
    if (error) { message(error); return; }
    message('Checking your guide’s calendar…');
    timer = setTimeout(check, 250);
  }
  if (window.Litepicker) {
    picker = new Litepicker({
      element: start, elementEnd: end, singleMode: false,
      autoApply: true, allowRepick: true, format: 'YYYY-MM-DD',
      minDate: isoToday, numberOfMonths: 1, numberOfColumns: 1,
      selectForward: true, lockDaysInclusivity: '[]', disallowLockDaysInRange: true,
      lockDays: blocked.map(range => [range.from, range.to]),
    });
    picker.on('selected', changed);
  } else {
    start.type = end.type = 'date';
    start.min = end.min = isoToday;
  }
  [start, end, persons, ...extras].forEach(el => {
    el.addEventListener('input', changed);
    el.addEventListener('change', changed);
  });
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (submitting) return;
    clearTimeout(timer);
    if (!form.reportValidity()) return;
    const before = selection();
    if (!await check() || before !== selection()) return;
    if (form.dataset.authenticated !== 'true') {
      const next = new URL(location.href);
      next.searchParams.set('start_date', start.value);
      next.searchParams.set('end_date', end.value);
      next.searchParams.set('persons', persons.value);
      next.searchParams.delete('autobook');
      const login = new URL(form.dataset.loginUrl, location.origin);
      login.searchParams.set('next', next.pathname + next.search);
      location.assign(login);
      return;
    }
    submitting = true;
    button.disabled = true;
    message('Sending your request. Please wait…');
    HTMLFormElement.prototype.submit.call(form);
  });
  window.addEventListener('pageshow', () => { submitting = false; changed(); });
  renderBlocked();
  changed();
});
