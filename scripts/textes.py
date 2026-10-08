"""Ce que contient un texte de loi et pourquoi il est proposé, d'après le texte déposé à l'Assemblée nationale.

Pour chaque dossier, le texte déposé (projet ou proposition de loi) est lu sur le site de l'Assemblée
(https://www.assemblee-nationale.fr/dyn/docs/<identifiant>.raw). On en garde, mot pour mot :
- le début de l'exposé des motifs, c'est-à-dire les raisons données par les auteurs ;
- les paragraphes où les auteurs présentent leurs articles (« L'article 1er… ») ;
- le nombre d'articles du texte.
Un texte déposé ne change plus : chaque extraction est gardée en cache et n'est faite qu'une fois.
Sortie : site/textes/<législature>/<dossier>.json, chargé par la page de la loi.
"""
import html, json, os, re, time, urllib.error, urllib.request

URL = "https://www.assemblee-nationale.fr/dyn/docs/{}.raw"
MAX_OCTETS = 4_000_000


def texte_brut(h):
    h = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", h, flags=re.S | re.I)
    h = re.sub(r"<sup[^>]*>.*?</sup>", "", h, flags=re.S | re.I)          # appels de notes
    h = re.sub(r"<br\s*/?>|</?(?:p|div|h\d|li|tr|td|th|table|ul|ol|section|article|header|footer|blockquote)\b[^>]*>", "\n", h, flags=re.I)
    t = html.unescape(re.sub(r"<[^>]+>", "", h))
    t = t.replace("’", "’").replace("\xa0", " ")
    t = re.sub(r"[ \t ]+", " ", t)
    t = re.sub(r"\b([IVX]+|1) er\b", r"\1er", t)
    return "\n".join(l.strip() for l in t.split("\n") if l.strip())


def nettoyer(p):
    p = re.sub(r"\s*\(\s*\[?\d{1,3}\]?\s*\)", "", p)      # « ([1]) », « (1) »
    p = re.sub(r"\[\d{1,3}\]", "", p)                       # « [8] »
    p = re.sub(r"(?<=[a-zé»)%])\d{1,2}(?=[\s,.;:])", "", p)  # appel de note collé au mot
    return re.sub(r"\s+", " ", p).strip()


ARTICLE = re.compile(r"^(?:Article\s+(?:1\s*er|premier|unique|\d+(?:\s+(?:bis|ter|quater|quinquies|sexies|septies|octies|nonies|decies|undecies|duodecies|terdecies))?(?:\s+[A-Z])?)|Art\.\s*\d+)(?:\s*\((?:nouveau|supprimé)\))?\s*$", re.I)
# paragraphes où les auteurs présentent LEURS articles (et non un article de loi existant : « l'article 13 de la loi du… »)
PRESENTE = re.compile(r"^(?:L[’']article\s+(?:1er|premier|unique|\d{1,3}(?:\s+(?:bis|ter|quater))?)(?!\s+(?:de la loi|du code|de l[’']ordonnance|de la Constitution|du décret|de la directive|du règlement))\b"
                      r"|Les articles\s+\d|Article\s+(?:1er|\d+|unique)\s*[:.–-]|Le (?:titre|chapitre)\s+(?:[IVX]+|premier|1er|\d)"
                      r"|La présente proposition de loi (?:vise|a pour|poursuit|propose|prévoit|comporte|entend|crée|instaure)|Le présent projet de loi (?:vise|a pour|comporte|prévoit|poursuit|propose|entend))", re.I)


def extraire(h):
    t = texte_brut(h)
    lignes = t.split("\n")
    debut = next((i for i, l in enumerate(lignes) if re.fullmatch(r"EXPOS[ÉE] DES MOTIFS\.?", l.strip(), re.I)), None)
    # début du dispositif : premier « Article 1er / Article unique » seul sur sa ligne, après l'exposé
    a0 = (debut or 0) + 1
    fin = next((i for i in range(a0, len(lignes)) if ARTICLE.match(lignes[i])), None)
    expose = []
    if debut is not None:
        stop = fin if fin is not None else len(lignes)
        # on s'arrête aussi au titre « PROJET DE LOI » / « PROPOSITION DE LOI » qui précède le dispositif
        for i in range(debut + 1, stop):
            l = lignes[i]
            if re.fullmatch(r"(PROJET|PROPOSITION) DE LOI.*", l) and i > debut + 3:
                break
            if re.fullmatch(r"Mesdames,? Messieurs,?", l, re.I) or len(l) < 25 and not l.endswith("."):
                continue
            expose.append(nettoyer(l))
    expose = [p for p in expose if len(p) > 40 and not re.search(r"délibéré en Conseil des ministres|sera présenté à l[’']Assemblée nationale|Fait à Paris, le", p)]
    n_articles = sum(1 for l in lignes[(fin or 0):] if ARTICLE.match(l)) if fin is not None else 0
    plan = [p for p in expose if PRESENTE.match(p)]
    intro = [p for p in expose if p not in plan]
    garde, total = [], 0
    for p in intro:
        if total > 3500:
            break
        garde.append(couper(p, 1200))
        total += len(p)
    return {"e": garde, "p": [couper(p, 600) for p in plan[:14]], "n": n_articles}


def couper(p, n):
    if len(p) <= n:
        return p
    k = p.rfind(". ", 0, n)
    if k > n * 0.5:
        return p[:k + 1]
    return p[:p.rfind(" ", 0, n)].rstrip(" ,;:") + "…"


def lire(uid):
    req = urllib.request.Request(URL.format(uid), headers={"User-Agent": "Mozilla/5.0 (compatible; AuxVoix/1.0; +https://aux-voix.github.io)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        brut = r.read(MAX_OCTETS)
    return brut.decode("utf-8", errors="replace")


def construire_textes(site_dir, cache_dir, lois_par_leg, max_nouveaux=350, duree_max=900):
    """lois_par_leg : {législature: [(id du dossier, identifiant du texte déposé, date de dernière activité)]}"""
    os.makedirs(cache_dir, exist_ok=True)
    debut, nouveaux, echecs, ecrits, absents = time.time(), 0, 0, 0, 0
    for leg, L in lois_par_leg.items():
        dossier = os.path.join(site_dir, "textes", str(leg))
        os.makedirs(dossier, exist_ok=True)
        for ident, uid, _ in sorted(L, key=lambda x: x[2] or "", reverse=True):  # les textes actifs d'abord
            if not uid or not re.fullmatch(r"[A-Z0-9]+", uid):
                continue
            cache = os.path.join(cache_dir, uid + ".json")
            x = None
            if os.path.exists(cache):
                try:
                    x = json.load(open(cache, encoding="utf-8"))
                except Exception:
                    x = None
            if x is None and nouveaux < max_nouveaux and time.time() - debut < duree_max and echecs < 25 and absents < 120:
                try:
                    x = extraire(lire(uid))
                    x["u"] = uid
                    json.dump(x, open(cache, "w", encoding="utf-8"), ensure_ascii=False)
                    nouveaux += 1
                    time.sleep(0.4)
                except urllib.error.HTTPError as e:
                    if e.code == 404:      # texte déposé mais pas encore mis en ligne : on réessaiera
                        absents += 1
                    else:
                        echecs += 1
                except Exception:
                    echecs += 1
            if x is not None:
                json.dump(x, open(os.path.join(dossier, ident + ".json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
                ecrits += 1
    return ecrits, nouveaux, echecs, absents
