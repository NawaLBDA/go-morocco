document.addEventListener('DOMContentLoaded', () => {
  const metadata = JSON.parse(document.getElementById('departure-tour-data')?.textContent || '{}');
  const tourField = document.getElementById('id_tour');
  const note = document.getElementById('departure-programme-note');
  const maxField = document.getElementById('id_max_days');
  const dateValue = value => /^\d{4}-\d{2}-\d{2}$/.test(value) ? new Date(`${value}T00:00:00Z`) : null;
  const iso = date => date.toISOString().slice(0, 10);
  const tour = () => metadata[tourField?.value || note?.dataset.currentTour] || {};
  const limit = () => Number(maxField?.value || tour().days || 5);
  function update(start, recalculate) {
    const end = document.querySelector(`[name="${start.name.replace(/start_date$/, 'end_date')}"]`);
    const date = dateValue(start.value);
    if (!end || !date || !Number.isInteger(limit()) || limit() < 1) return;
    const last = new Date(date);
    last.setUTCDate(last.getUTCDate() + limit() - 1);
    end.min = iso(date);
    end.max = iso(last);
    if (recalculate || !end.value) end.value = iso(last);
    preview();
  }
  function preview() {
    const output = document.getElementById('departure-programme-preview');
    const start = dateValue(document.getElementById('id_start_date')?.value || '');
    const end = dateValue(document.getElementById('id_end_date')?.value || '');
    if (!output) return;
    output.replaceChildren();
    if (!start || !end || end < start) return;
    const count = Math.round((end - start) / 86400000) + 1;
    if (count > limit()) return;
    const list = document.createElement('ol');
    for (let day = 1; day <= count; day++) {
      const date = new Date(start);
      date.setUTCDate(date.getUTCDate() + day - 1);
      const item = document.createElement('li');
      const activities = tour().programme?.[String(day)] || [];
      item.textContent = `${iso(date)} · Day ${day}: ${activities.join(', ') || 'No activities entered for this day yet.'}`;
      list.append(item);
    }
    output.append(list);
  }
  document.addEventListener('change', event => {
    const field = event.target;
    if (field.name?.endsWith('start_date')) update(field, true);
    else if (field === tourField) {
      const start = document.getElementById('id_start_date');
      if (start) update(start, true);
    } else if (field.name?.endsWith('end_date')) preview();
    else if (field === maxField) {
      document.querySelectorAll('input[name$="-start_date"]').forEach(start => {
        const id = document.querySelector(`[name="${start.name.replace(/start_date$/, 'id')}"]`);
        update(start, !id?.value);
      });
    }
  });
  document.querySelectorAll('input[name$="start_date"]').forEach(start => update(start, false));
});
