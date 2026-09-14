/* Cursor-follow spotlight for [data-spotlight] shells. */
(function () {
    var DEFAULT_SIZE = 124;
    var LERP = 0.18;

    function setup(el) {
        var spot = el.querySelector("[data-spotlight-beam]");
        if (!spot) return;

        var size = Number(spot.getAttribute("data-size")) || DEFAULT_SIZE;
        var targetX = -size;
        var targetY = -size;
        var x = targetX;
        var y = targetY;
        var hovering = false;
        var raf = 0;

        function tick() {
            x += (targetX - x) * LERP;
            y += (targetY - y) * LERP;
            spot.style.transform = "translate(" + x + "px, " + y + "px)";
            if (hovering || Math.abs(targetX - x) > 0.4 || Math.abs(targetY - y) > 0.4) {
                raf = window.requestAnimationFrame(tick);
            } else {
                raf = 0;
            }
        }

        function ensureTick() {
            if (!raf) raf = window.requestAnimationFrame(tick);
        }

        el.addEventListener("mouseenter", function () {
            hovering = true;
            el.classList.add("is-spotlight-on");
            ensureTick();
        });

        el.addEventListener("mouseleave", function () {
            hovering = false;
            el.classList.remove("is-spotlight-on");
        });

        el.addEventListener("mousemove", function (event) {
            var rect = el.getBoundingClientRect();
            targetX = event.clientX - rect.left - size / 2;
            targetY = event.clientY - rect.top - size / 2;
            ensureTick();
        });
    }

    function init() {
        if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
        document.querySelectorAll("[data-spotlight]").forEach(setup);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
