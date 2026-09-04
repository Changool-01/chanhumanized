/**
 * Read Django's CSRF token from the csrftoken cookie so fetch() POSTs succeed.
 */
(function () {
    "use strict";

    /**
     * Return a cookie value by name, or an empty string if missing.
     * @param {string} name
     * @returns {string}
     */
    function readCookie(name) {
        const parts = document.cookie.split(";");
        for (let i = 0; i < parts.length; i += 1) {
            const piece = parts[i].trim();
            if (piece.startsWith(name + "=")) {
                return decodeURIComponent(piece.slice(name.length + 1));
            }
        }
        return "";
    }

    /**
     * CSRF header value for this page.
     * @returns {string}
     */
    function csrfToken() {
        return readCookie("csrftoken");
    }

    window.chanCsrf = {
        readCookie: readCookie,
        csrfToken: csrfToken,
    };
})();
