/**
 * Workspace behaviour: live word count, Humanize fetch, copy, download,
 * diff highlight toggle, and regenerate.
 */
(function () {
    "use strict";

    /**
     * Wire the split workspace once the DOM is ready.
     * @returns {void}
     */
    function initWorkspace() {
        const root = document.querySelector("[data-workspace]");
        if (!root) {
            return;
        }

        const form = root.querySelector("[data-humanize-form]");
        const original = root.querySelector("[data-original]");
        const countEl = root.querySelector("[data-word-count]");
        const capEl = root.querySelector("[data-word-cap]");
        const submit = root.querySelector("[data-humanize-submit]");
        const regenerate = root.querySelector("[data-regenerate]");
        const banner = root.querySelector("[data-banner]");
        const empty = root.querySelector("[data-empty]");
        const result = root.querySelector("[data-result]");
        const showDiff = root.querySelector("[data-show-diff]");
        const copyBtn = root.querySelector("[data-copy]");
        const downloadBtn = root.querySelector("[data-download]");
        const usedEl = document.querySelector("[data-quota-used]");
        const remainingEl = document.querySelector("[data-quota-remaining]");
        const requestLimit = Number(root.getAttribute("data-request-limit") || "2000");
        const humanizeUrl = root.getAttribute("data-humanize-url");

        let lastHumanizedText = "";
        let lastDiffHtml = "";

        /**
         * Update the live counter and over-limit styling.
         * @returns {void}
         */
        function refreshCount() {
            const n = window.chanWordcount.countWords(original.value);
            countEl.textContent = String(n);
            capEl.parentElement.classList.toggle("is-over", n > requestLimit);
        }

        /**
         * Show or hide the status banner.
         * @param {string} message
         * @param {boolean} loading
         * @returns {void}
         */
        function showBanner(message, loading) {
            if (!message) {
                banner.hidden = true;
                banner.textContent = "";
                banner.classList.remove("is-loading");
                return;
            }
            banner.hidden = false;
            banner.textContent = message;
            banner.classList.toggle("is-loading", Boolean(loading));
        }

        /**
         * Display the result according to the Show changes toggle.
         * @returns {void}
         */
        function renderResult() {
            if (!lastHumanizedText) {
                empty.hidden = false;
                result.hidden = true;
                result.textContent = "";
                result.innerHTML = "";
                copyBtn.disabled = true;
                downloadBtn.disabled = true;
                regenerate.disabled = true;
                return;
            }
            empty.hidden = true;
            result.hidden = false;
            regenerate.disabled = false;
            if (showDiff.checked && lastDiffHtml) {
                result.innerHTML = lastDiffHtml;
            } else {
                result.textContent = lastHumanizedText;
            }
            copyBtn.disabled = false;
            downloadBtn.disabled = false;
        }

        /**
         * Store a new humanize result and update the pane.
         * @param {string} text
         * @param {string} diffHtml
         * @returns {void}
         */
        function setResult(text, diffHtml) {
            lastHumanizedText = text || "";
            lastDiffHtml = diffHtml || "";
            renderResult();
        }

        /**
         * Refresh the quota bar after a successful (or rejected) call.
         * @param {object} snapshot
         * @returns {void}
         */
        function updateQuota(snapshot) {
            if (!snapshot || snapshot.is_pro) {
                return;
            }
            if (usedEl) {
                usedEl.textContent = Number(snapshot.used).toLocaleString("en-US");
            }
            if (remainingEl && snapshot.remaining !== null && snapshot.remaining !== undefined) {
                remainingEl.textContent = Number(snapshot.remaining).toLocaleString("en-US");
            }
        }

        /**
         * POST the form to Django and show the result.
         * @param {boolean} isRegenerate
         * @returns {Promise<void>}
         */
        async function submitHumanize(isRegenerate) {
            showBanner(isRegenerate ? "Trying a new version…" : "Humanizing… this can take a few seconds.", true);
            submit.disabled = true;
            regenerate.disabled = true;
            const body = new FormData(form);
            body.set("original_text", original.value);
            if (isRegenerate) {
                body.set("regenerate", "1");
            }

            try {
                const response = await fetch(humanizeUrl, {
                    method: "POST",
                    headers: {
                        "X-CSRFToken": window.chanCsrf.csrfToken() ||
                            (form.querySelector("[name=csrfmiddlewaretoken]") || {}).value ||
                            "",
                    },
                    body: body,
                });
                const data = await response.json();
                updateQuota(data.snapshot);
                if (!data.ok) {
                    showBanner(data.error || "The rewrite failed.");
                    return;
                }
                setResult(data.humanized_text, data.diff_html);
                showBanner("");
            } catch (err) {
                showBanner("Could not reach the server. Check your connection and try again.");
            } finally {
                submit.disabled = false;
                regenerate.disabled = !lastHumanizedText;
            }
        }

        /**
         * Handle the main Humanize submit.
         * @param {Event} event
         * @returns {void}
         */
        function onSubmit(event) {
            event.preventDefault();
            submitHumanize(false);
        }

        /**
         * Regenerate a different version of the same text.
         * @returns {void}
         */
        function onRegenerate() {
            submitHumanize(true);
        }

        /**
         * Swap between plain text and highlighted changes.
         * @returns {void}
         */
        function onToggleDiff() {
            renderResult();
        }

        /**
         * Copy the humanized text to the clipboard.
         * @returns {Promise<void>}
         */
        async function onCopy() {
            if (!lastHumanizedText) {
                return;
            }
            try {
                await navigator.clipboard.writeText(lastHumanizedText);
                copyBtn.textContent = "Copied";
                setTimeout(function () {
                    copyBtn.textContent = "Copy";
                }, 1600);
            } catch (err) {
                showBanner("Copy failed. Select the text and copy it manually.");
            }
        }

        /**
         * Download the humanized text as a .txt file.
         * @returns {void}
         */
        function onDownload() {
            if (!lastHumanizedText) {
                return;
            }
            const blob = new Blob([lastHumanizedText], { type: "text/plain;charset=utf-8" });
            const url = URL.createObjectURL(blob);
            const link = document.createElement("a");
            link.href = url;
            link.download = "chan-humanized.txt";
            link.click();
            URL.revokeObjectURL(url);
        }

        original.addEventListener("input", refreshCount);
        form.addEventListener("submit", onSubmit);
        regenerate.addEventListener("click", onRegenerate);
        showDiff.addEventListener("change", onToggleDiff);
        copyBtn.addEventListener("click", onCopy);
        downloadBtn.addEventListener("click", onDownload);
        refreshCount();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initWorkspace);
    } else {
        initWorkspace();
    }
})();
