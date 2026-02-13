document.addEventListener("DOMContentLoaded", function () {

    /* =============================
       THEME TOGGLE
    ============================== */
    const themeToggle = document.getElementById('themeToggle');
    const htmlElement = document.documentElement;
    const themeIcon = document.getElementById('themeIcon');

    function updateIcon(theme) {
        if (themeIcon) themeIcon.innerText = theme === 'light' ? '🌑' : '☀️';
    }

    const savedTheme = localStorage.getItem('theme') || 'light';
    htmlElement.setAttribute('data-bs-theme', savedTheme);
    updateIcon(savedTheme);

    themeToggle?.addEventListener('click', () => {
        const newTheme = htmlElement.getAttribute('data-bs-theme') === 'light' ? 'dark' : 'light';
        htmlElement.setAttribute('data-bs-theme', newTheme);
        localStorage.setItem('theme', newTheme);
        updateIcon(newTheme);
    });

    /* =============================
       FONT SIZE
    ============================== */
    function applyFont(size) {
        document.body.classList.remove('font-medium', 'font-large');
        if (size !== 'normal') document.body.classList.add('font-' + size);
    }

    const savedFontSize = localStorage.getItem('user-font-size') || 'normal';
    applyFont(savedFontSize);

    const fontSelector = document.getElementById('fontSelector');
    if (fontSelector) {
        fontSelector.value = savedFontSize;
        fontSelector.addEventListener('change', (e) => {
            localStorage.setItem('user-font-size', e.target.value);
            applyFont(e.target.value);
        });
    }

    /* =============================
       AUTO HIDE ALERTS
    ============================== */
    const alerts = document.querySelectorAll('.auto-alert');
    if (alerts.length > 0) {
        setTimeout(() => {
            alerts.forEach(alert => {
                alert.classList.remove('show');
                alert.style.opacity = "0";
                setTimeout(() => alert.remove(), 500);
            });
        }, 3000);
    }

});
