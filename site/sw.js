/* Aux Voix : fonctionnement hors connexion.
   Pages et données : réseau d'abord (toujours la version la plus récente), copie locale si le réseau ne répond pas.
   Polices, icônes et photos : copie locale d'abord, rafraîchie en arrière-plan. Rien n'est envoyé à un tiers. */
const VERSION = "av-1";
const BASE = ["./", "index.html", "favicon.svg", "manifest.webmanifest", "icones/icone-192.png", "icones/icone-512.png",
  "fonts/Lexend.ttf", "fonts/SourceSans3.ttf", "fonts/SourceSans3-Italic.ttf"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(VERSION).then(c => Promise.all(BASE.map(u => c.add(u).catch(() => null)))).then(() => self.skipWaiting()));
});
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(K => Promise.all(K.filter(k => k !== VERSION).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});

function reseauDabord(req, cle) {
  const delai = new Promise(res => setTimeout(() => res(null), 6000));
  const reseau = fetch(req).then(r => {
    if (r && r.ok) { const copie = r.clone(); caches.open(VERSION).then(c => c.put(cle || req, copie)); }
    return r;
  });
  return Promise.race([reseau.catch(() => null), delai]).then(r => r || caches.match(cle || req, { ignoreSearch: true })
    .then(m => m || reseau.catch(() => caches.match("index.html"))));
}
function copieDabord(req) {
  return caches.match(req).then(m => {
    const maj = fetch(req).then(r => { if (r && r.ok) { const copie = r.clone(); caches.open(VERSION).then(c => c.put(req, copie)); } return r; }).catch(() => null);
    return m || maj.then(r => r || new Response("", { status: 504 }));
  });
}
self.addEventListener("fetch", e => {
  const req = e.request, url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== self.location.origin) return;
  if (/\/(flux|sitemap)|\.xml$|robots\.txt$/.test(url.pathname)) return;
  if (req.mode === "navigate") {
    const accueil = url.pathname.endsWith("/") || url.pathname.endsWith("/index.html");
    e.respondWith(reseauDabord(req, accueil ? "index.html" : undefined));
    return;
  }
  if (/\.json$/.test(url.pathname)) { e.respondWith(reseauDabord(req)); return; }
  if (/\.(ttf|woff2?|png|jpe?g|svg|webp|webmanifest)$/.test(url.pathname)) { e.respondWith(copieDabord(req)); return; }
});
