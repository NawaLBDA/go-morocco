/* Scheduled departures: the server validates the programme and locks the guide calendar. */
document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('booking-form');
  if (!form?.dataset.availabilityUrl) return;
  const departure = form.querySelector('[name="departure_id"]');
  const start = form.querySelector('[name="start_date"]');
  const end = form.querySelector('[name="end_date"]');
  const persons = form.querySelector('[name="persons"]');
  const button = document.getElementById('confirmCashBtn');
  const status = document.getElementById('guide-availability-status');
  const total = document.getElementById('live-price');
  const days = document.getElementById('live-days');
  const count = Number(document.getElementById('booking-days').value);
  const packagePriced = form.dataset.packagePriced === 'true';
  const base = Number(document.getElementById('base-price').value);
  const extras = [...document.querySelectorAll('.extra-activity-toggle')];
  let timer, revision = 0, submitting = false, availabilityNotified = false;
  const selection = () => new URLSearchParams(new FormData(form)).toString();
  function message(text, state = '') {
    status.textContent = text;
    status.dataset.state = state;
    status.hidden = state === 'available';
    if (state === 'available' && !availabilityNotified) {
      window.showSiteToast?.(`${document.getElementById('booking-approval-notice')?.textContent || ''} ${text}`, 'info');
      availabilityNotified = true;
    }
  }
  function localError() {
    if (!departure.value || !count) return 'Choose a scheduled departure to see your programme and total.';
    if (!Number.isInteger(Number(persons.value)) || Number(persons.value) < Number(persons.min || 1)) return `This package requires at least ${persons.min || 1} travelers.`;
    if (persons.max && Number(persons.value) > Number(persons.max)) return `This departure accommodates up to ${persons.max} travelers.`;
    return '';
  }
  function price() {
    const travelers = Number(persons.value);
    days.textContent = count ? `${count} ${count === 1 ? 'day' : 'days'}` : '?';
    if (localError()) { total.textContent = '?'; return; }
    let amount = base * (packagePriced ? 1 : count) * travelers;
    extras.filter(el => el.checked).forEach(el => {
      amount += Number(el.dataset.price || 0) * travelers * (el.dataset.perNight === '1' ? count : 1);
    });
    if (travelers > 5 && !packagePriced) amount *= .9;
    total.textContent = `${amount.toFixed(2)} $`;
  }
  async function check() {
    const current = ++revision;
    button.disabled = true;
    const error = localError();
    if (error) { message(error); return false; }
    message('Checking departure availability?');
    const url = new URL(form.dataset.availabilityUrl, location.origin);
    url.searchParams.set('departure_id', departure.value);
    url.searchParams.set('tour_id', document.getElementById('booking-tour-id').value);
    url.searchParams.set('start_date', start.value);
    url.searchParams.set('end_date', end.value);
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch(url, { cache: 'no-store', headers: { Accept: 'application/json' }, signal: controller.signal });
      const data = await response.json();
      if (current !== revision) return false;
      if (!response.ok) throw new Error(data.error || 'Availability could not be checked. Please reload to try again.');
      if (data.days !== count) throw new Error('This programme has changed. Please reload to see the updated days and price.');
      message(data.message, data.available ? 'available' : 'error');
      button.disabled = !data.available;
      return data.available;
    } catch (error) {
      if (current !== revision) return false;
      message(error.name === 'AbortError' || error.message === 'Failed to fetch' ? 'Connection interrupted. Please reload to check this departure again.' : error.message, 'error');
      return false;
    } finally {
      clearTimeout(timeout);
    }
  }
  function changed() {
    if (persons.value && persons.max && Number(persons.value) > Number(persons.max)) {
      persons.value = persons.max;
      window.showSiteToast?.(`Maximum ${persons.max} travelers for this departure.`, 'info');
    }
    revision++;
    clearTimeout(timer);
    button.disabled = true;
    price();
    const error = localError();
    if (error) { message(error); return; }
    message('Checking departure availability?');
    timer = setTimeout(check, 250);
  }
  [persons, ...extras].forEach(el => {
    el.addEventListener('input', changed);
    el.addEventListener('change', () => {
      if (el === persons && persons.value && Number(persons.value) < Number(persons.min || 1)) {
        persons.value = persons.min || '1';
        window.showSiteToast?.(`Minimum ${persons.min || 1} travelers for this package.`, 'info');
      }
      changed();
    });
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
      next.searchParams.set('departure_id', departure.value);
      next.searchParams.set('persons', persons.value);
      next.searchParams.set('payment_method', form.querySelector('[name="payment_method"]:checked').value);
      next.searchParams.delete('extra_activity_ids');
      extras.filter(el => el.checked).forEach(el => next.searchParams.append('extra_activity_ids', el.value));
      next.searchParams.delete('autobook');
      const login = new URL(form.dataset.loginUrl, location.origin);
      login.searchParams.set('next', next.pathname + next.search);
      location.assign(login);
      return;
    }
    submitting = true;
    button.disabled = true;
    message('Sending your request. Please wait?');
    HTMLFormElement.prototype.submit.call(form);
  });
  window.addEventListener('pageshow', () => { submitting = false; changed(); });
  changed();
});
