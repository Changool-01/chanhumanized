/**
 * Word counter — must match apps/humanizer/services/wordcount.py
 * (whitespace-separated tokens).
 */
(function () {
    "use strict";

    /**
     * Count whitespace-separated words in a string.
     * @param {string} text
     * @returns {number}
     */
    function countWords(text) {
        if (!text || !String(text).trim()) {
            return 0;
        }
        return String(text).trim().split(/\s+/).length;
    }

    window.chanWordcount = {
        countWords: countWords,
    };
})();
