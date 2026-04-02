
// Lightweight reveal-on-scroll animations.
// Adds `.is-visible` to any element with `.reveal` when it enters the viewport.
document.addEventListener('DOMContentLoaded', () => {
	const targets = document.querySelectorAll('.reveal');
	if (!targets.length) return;

	// If the browser doesn't support IntersectionObserver, just show everything.
	if (!('IntersectionObserver' in window)) {
		targets.forEach(el => el.classList.add('is-visible'));
		return;
	}

	const observer = new IntersectionObserver(
		(entries) => {
			entries.forEach(entry => {
				if (entry.isIntersecting) {
					entry.target.classList.add('is-visible');
					observer.unobserve(entry.target);
				}
			});
		},
		{ root: null, threshold: 0.12 }
	);

	targets.forEach(el => observer.observe(el));
});

