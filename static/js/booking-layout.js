document.addEventListener('DOMContentLoaded', () => {
  const sidebar = document.getElementById('tour-booking-card');
  if (!sidebar) return;
  const desktop = matchMedia('(min-width: 992px)');
  let queued = false;
  function resize() {
    queued = false;
    if (!desktop.matches) {
      sidebar.style.removeProperty('max-height');
      return;
    }
    const top = Math.max(24, sidebar.getBoundingClientRect().top);
    sidebar.style.maxHeight = `${Math.max(180, window.innerHeight - top - 24)}px`;
  }
  function schedule() {
    if (!queued) { queued = true; requestAnimationFrame(resize); }
  }
  window.addEventListener('scroll', schedule, { passive: true });
  window.addEventListener('resize', schedule);
  window.addEventListener('load', schedule);
  document.fonts?.ready.then(schedule);
  resize();
});
