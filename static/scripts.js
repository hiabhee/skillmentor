document.addEventListener('DOMContentLoaded', () => {
    window.setTimeout(() => {
        document.querySelectorAll('.flash').forEach((flash) => {
            flash.classList.add('is-dismissed');
            window.setTimeout(() => flash.remove(), 220);
        });
    }, 6000);
});
