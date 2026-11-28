/* Hero rotator: crossfade, default first, then random.
   Ported verbatim from the single-file source's inline <script> (centre
   column, after the hero figure). 24 slides in a JS array; per-image link
   slots are all empty (assign only when the owner names them). The default
   slide (disc-craft-earth-night.webp) shows first, then the rest shuffle;
   crossfade is the two-<img> .on class swap; 11,000 ms interval; pauses
   when the tab is hidden; disabled when prefers-reduced-motion. */
/* ---------- Hero rotator: crossfade, default first, then random ---------- */
(function () {
  var slides = [{"src": "assets/hero/disc-craft-earth-night.webp", "alt": "A smooth, elegant lenticular silver disc craft above Earth at night", "link": ""}, {"src": "assets/hero/triangular-craft.jpg", "alt": "Triangular CTP Space Systems craft", "link": ""}, {"src": "assets/hero/craft-earth.jpg", "alt": "Cylindrical craft over Earth", "link": ""}, {"src": "assets/hero/ufo-trees.jpg", "alt": "UFO over trees, black and white", "link": ""}, {"src": "assets/hero/ufo-disc.jpg", "alt": "UFO disc, centred", "link": ""}, {"src": "assets/hero/craft-interior.jpg", "alt": "Craft interior cabin", "link": ""}, {"src": "assets/hero/cylindrical-craft.jpg", "alt": "Cylindrical craft in space", "link": ""}, {"src": "assets/hero/ctp-space-cruiser.jpg", "alt": "CTP space cruiser", "link": ""}, {"src": "assets/hero/ctp-space-systems-cruiser.jpg", "alt": "CTP Space Systems, CTP Space Cruiser", "link": ""}, {"src": "assets/hero/ufo-airport.jpg", "alt": "UFO over airport", "link": ""}, {"src": "assets/hero/ufo-airport-2.jpg", "alt": "UFO over airport, second view", "link": ""}, {"src": "assets/hero/blue-craft-night.jpg", "alt": "CTP Space Cruiser™", "link": ""}, {"src": "assets/hero/cigar-craft-city.jpg", "alt": "Cigar craft over city", "link": ""}, {"src": "assets/hero/ufo-lights-trees.jpg", "alt": "CTPcraft w/ CEMAS™ Arrays", "link": ""}, {"src": "assets/hero/uap-flir.jpg", "alt": "CTPcraft maneuvers", "link": ""}, {"src": "assets/hero/triangular-craft-top.jpg", "alt": "Triangular craft, top view", "link": ""}, {"src": "assets/hero/ctp-space-systems-saucer.jpg", "alt": "CTP Space Systems saucer craft", "link": ""}, {"src": "assets/hero/ctp-spaceliner.jpg", "alt": "CTP Space Systems, CTP Spaceliner", "link": ""}, {"src": "assets/hero/ctp-space-liner.jpg", "alt": "CTP Spaceliner™", "link": ""}, {"src": "assets/hero/ctp-industrial-space-platform.jpg", "alt": "CTP Space Systems, CTP Industrial Space Platform (CTPISP)", "link": ""}, {"src": "assets/hero/ctp-space-platform.jpg", "alt": "CTP Space Systems platform", "link": ""}, {"src": "assets/hero/ctp-diamond-craft.jpg", "alt": "CTP diamond craft", "link": ""}, {"src": "assets/hero/ctp-diamond-craft-dark.jpg", "alt": "CTP Space Systems diamond craft", "link": ""}, {"src": "assets/hero/x1-heavy-lift.jpg", "alt": "X-1 Heavy Lift Fuselage, CTP Space Systems", "link": ""}];
  var link = document.getElementById("hero-link");
  var a = document.getElementById("hero-img-a");
  var b = document.getElementById("hero-img-b");
  var cur = a, nxt = b, idx = 0;
  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  function shuffle(arr) { for (var i = arr.length - 1; i > 0; i--) { var j = Math.floor(Math.random() * (i + 1)); var t = arr[i]; arr[i] = arr[j]; arr[j] = t; } return arr; }
  var order = [slides[0]].concat(shuffle(slides.slice(1)));
  function applyLink(s) { if (s.link) { link.setAttribute("href", s.link); link.style.cursor = "pointer"; } else { link.removeAttribute("href"); link.style.cursor = "default"; } }
  function preload(src) { var im = new Image(); im.src = src; }
  function show(i) { var s = order[i]; nxt.src = s.src; nxt.alt = s.alt; nxt.classList.add("on"); cur.classList.remove("on"); applyLink(s); var t = cur; cur = nxt; nxt = t; preload(order[(i + 1) % order.length].src); }
  a.src = order[0].src; a.alt = order[0].alt; a.classList.add("on"); applyLink(order[0]); preload(order[1].src);
  if (reduce) return;
  var timer = null;
  function next() { idx = (idx + 1) % order.length; if (idx === 0) { order = [order[0]].concat(shuffle(order.slice(1))); } show(idx); }
  function start() { if (!timer) timer = setInterval(next, 11000); }
  function stop() { if (timer) { clearInterval(timer); timer = null; } }
  document.addEventListener("visibilitychange", function () { if (document.hidden) stop(); else start(); });
  start();
})();

