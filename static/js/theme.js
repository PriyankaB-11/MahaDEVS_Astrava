// Theme toggle: dark ↔ light, persisted in localStorage
(function () {
    const saved = localStorage.getItem('airaware-theme');
    if (saved) document.documentElement.setAttribute('data-theme', saved);
})();

function toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme');
    const next = current === 'light' ? 'dark' : 'light';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('airaware-theme', next);
}
