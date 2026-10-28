window.showSiteToast = (message, level = 'info') => {
  const stack = document.getElementById('site-toast-stack');
  if (!stack || !message) return;
  const toast = document.createElement('div');
  toast.className = `site-toast ${level === 'error' ? 'site-toast-error' : ''}`;
  toast.setAttribute('role', level === 'error' ? 'alert' : 'status');
  const text = document.createElement('span'); text.textContent = message;
  const close = document.createElement('button'); close.type = 'button'; close.textContent = '×';
  close.setAttribute('aria-label', 'Dismiss notification');
  close.addEventListener('click', () => toast.remove());
  toast.append(text, close); stack.append(toast);
  while (stack.children.length > 3) stack.firstElementChild.remove();
  let timeout = setTimeout(() => toast.remove(), 10000);
  toast.addEventListener('mouseenter', () => clearTimeout(timeout));
  toast.addEventListener('focusin', () => clearTimeout(timeout));
  toast.addEventListener('mouseleave', () => { timeout = setTimeout(() => toast.remove(), 10000); });
};
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-site-message]').forEach(message => window.showSiteToast(message.textContent, message.dataset.level));
  document.querySelectorAll('input[type="number"][max]').forEach(input => input.addEventListener('input', () => {
    if (input.value && Number(input.value) > Number(input.max)) {
      input.value = input.max;
      window.showSiteToast(`Maximum ${input.max} travelers for this departure.`);
    }
  }));
});
