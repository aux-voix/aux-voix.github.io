#!/usr/bin/env python3
"""Le Relevé : codes consolidés (Constitution, Code civil, Code pénal…) depuis la base officielle LEGI de la DILA
(Licence Ouverte). Archive complète + mises à jour quotidiennes, relues au plus une fois par semaine."""
import datetime, html, io, json, os, re, sys, tarfile, time, urllib.request
import xml.etree.ElementTree as ET

BASE = "https://echanges.dila.gouv.fr/OPENDATA/LEGI/"
UA = "LeReleve/2.0 (https://lereleve.github.io ; reutilisation de donnees ouvertes)"
# identifiant LEGI du code (et identifiant JORF d'origine, qui sert parfois de dossier), abréviation d'usage
CODES = [
    {"slug": "constitution", "ids": ["LEGITEXT000006071194", "JORFTEXT000000571356"], "abr": "Const.", "titre": "Constitution du 4 octobre 1958", "code": False},
    {"slug": "civil", "ids": ["LEGITEXT000006070721"], "abr": "C. civ.", "titre": "Code civil", "code": True},
    {"slug": "penal", "ids": ["LEGITEXT000006070719"], "abr": "C. pén.", "titre": "Code pénal", "code": True},
    {"slug": "procedure-civile", "ids": ["LEGITEXT000006070716"], "abr": "C. pr. civ.", "titre": "Code de procédure civile", "code": True},
    {"slug": "procedure-penale", "ids": ["LEGITEXT000006071154"], "abr": "C. pr. pén.", "titre": "Code de procédure pénale", "code": True},
    {"slug": "commerce", "ids": ["LEGITEXT000005634379"], "abr": "C. com.", "titre": "Code de commerce", "code": True},
    {"slug": "travail", "ids": ["LEGITEXT000006072050"], "abr": "C. trav.", "titre": "Code du travail", "code": True},
    {"slug": "consommation", "ids": ["LEGITEXT000006069565"], "abr": "C. consom.", "titre": "Code de la consommation", "code": True},
    {"slug": "justice-administrative", "ids": ["LEGITEXT000006070933"], "abr": "CJA", "titre": "Code de justice administrative", "code": True},
    {"slug": "relations-administration", "ids": ["LEGITEXT000031366350"], "abr": "CRPA", "titre": "Code des relations entre le public et l'administration", "code": True},
]
EN_VIGUEUR = ("VIGUEUR", "VIGUEUR_DIFF")


def obtenir(url, timeout=120):
    if url.startswith("file://"):
        return open(url[7:], "rb").read()
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=timeout) as r:
        return r.read()


def lister_archives():
    """Archive complète la plus récente, puis toutes les mises à jour postérieures, dans l'ordre."""
    local = os.environ.get("RELEVE_LEGI_LOCAL")
    if local:
        noms = sorted(os.listdir(local))
        racine = "file://" + os.path.abspath(local) + "/"
    else:
        page = obtenir(BASE).decode("utf-8", "replace")
        noms = sorted(set(re.findall(r'href="((?:Freemium_legi_global_|LEGI_)\d{8}-\d{6}\.tar\.gz)"', page)))
        racine = BASE
    globales = [n for n in noms if n.startswith("Freemium_legi_global_")]
    if not globales:
        raise RuntimeError("aucune archive complète LEGI trouvée")
    g = globales[-1]
    date_g = re.search(r"(\d{8}-\d{6})", g).group(1)
    incr = [n for n in noms if n.startswith("LEGI_") and re.search(r"(\d{8}-\d{6})", n).group(1) > date_g]
    return racine, g, incr


def texte_brut(el):
    """Contenu HTML d'un article -> paragraphes en texte simple."""
    if el is None:
        return ""
    brut = ET.tostring(el, encoding="unicode", method="xml")
    brut = re.sub(r"<br\s*/?>", "\n", brut)
    brut = re.sub(r"</(p|div|li|tr|h\d)>", "\n", brut)
    brut = re.sub(r"<[^>]+>", "", brut)
    brut = html.unescape(brut)
    lignes = [re.sub(r"[ \t\u00a0]+", " ", l).strip() for l in brut.split("\n")]
    out, vide = [], False
    for l in lignes:
        if l:
            out.append(l)
            vide = False
        elif not vide and out:
            out.append("")
            vide = True
    return "\n".join(out).strip()


def lire_article(data):
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return None
    if root.tag != "ARTICLE":
        return None
    g = lambda p: (root.findtext(p) or "").strip()
    art = {"id": g("META/META_COMMUN/ID"), "num": g("META/META_SPEC/META_ARTICLE/NUM"),
           "etat": g("META/META_SPEC/META_ARTICLE/ETAT"), "debut": g("META/META_SPEC/META_ARTICLE/DATE_DEBUT"),
           "fin": g("META/META_SPEC/META_ARTICLE/DATE_FIN"), "texte": texte_brut(root.find("BLOC_TEXTUEL/CONTENU")),
           "nota": texte_brut(root.find("NOTA/CONTENU")), "chemin": [], "liens": []}
    tm = root.find("CONTEXTE/TEXTE/TM")
    while tm is not None:
        t = tm.find("TITRE_TM")
        if t is not None and (t.text or "").strip():
            art["chemin"].append(re.sub(r"\s+", " ", t.text).strip())
        tm = tm.find("TM")
    for l in root.findall("LIENS/LIEN"):
        a = l.attrib
        if a.get("sens") == "cible" and a.get("typelien") in ("CREATION", "MODIFIE", "TRANSFERE", "DEPLACE", "CODIFIE"):
            art["liens"].append({"date": a.get("datesignatexte", ""), "type": a.get("typelien"), "titre": re.sub(r"\s+", " ", l.text or "").strip(),
                                 "cid": a.get("cidtexte", "")})
    return art if art["id"] and art["num"] else None


def parcourir(chemin_tar, motifs, articles, suppr):
    """Lit une archive en flux et garde les articles des codes choisis (une entrée par identifiant de version)."""
    n = 0
    with tarfile.open(chemin_tar, "r|gz") as tar:
        for m in tar:
            nom = m.name
            if m.isfile() and nom.endswith("liste_suppression_legi.dat"):
                f = tar.extractfile(m)
                for ligne in (f.read().decode("utf-8", "replace").splitlines() if f else []):
                    x = re.search(r"(LEGIARTI\d+)", ligne)
                    if x and any(mo in ligne for mo in motifs):
                        suppr.add(x.group(1))
                continue
            if not m.isfile() or "/article/" not in nom or not nom.endswith(".xml"):
                continue
            if not any(mo in nom for mo in motifs):
                continue
            f = tar.extractfile(m)
            a = lire_article(f.read()) if f else None
            if a:
                a["_motif"] = next(mo for mo in motifs if mo in nom)
                articles[a["id"]] = a
                n += 1
    return n


def cle_num(num):
    """Tri naturel des numéros d'article : 2 < 9 < 10, L. 121-1 < L. 121-10, 1240 < 1240-1."""
    parts = re.findall(r"\d+|[A-Za-z]+", num.replace("*", ""))
    return [(0, int(p)) if p.isdigit() else (1, p.lower()) for p in parts]


def version_issue_de(art):
    """Texte qui a donné à l'article sa rédaction actuelle : dernier lien signé avant l'entrée en vigueur."""
    ok = [l for l in art["liens"] if l["date"] and l["date"] <= (art["debut"] or "9999")]
    ok.sort(key=lambda l: l["date"])
    return ok[-1] if ok else (art["liens"][-1] if art["liens"] else None)


def construire_codes(site_dir, cache_dir):
    os.makedirs(cache_dir, exist_ok=True)
    etat_path = os.path.join(cache_dir, "codes-etat.json")
    out_dir = os.path.join(site_dir, "codes")
    os.makedirs(out_dir, exist_ok=True)
    try:
        etat = json.load(open(etat_path, encoding="utf-8"))
        age = (datetime.datetime.now(datetime.timezone.utc) - datetime.datetime.fromisoformat(etat["date"])).days
    except Exception:
        etat, age = None, 999
    cache_codes = os.path.join(cache_dir, "codes")
    if etat and age < 7 and os.environ.get("RELEVE_FORCER_CODES") != "1" and os.path.isdir(cache_codes):
        for nom in os.listdir(cache_codes):
            open(os.path.join(out_dir, nom), "wb").write(open(os.path.join(cache_codes, nom), "rb").read())
        print(f"Codes : cache de {age} jour(s) réutilisé")
        return
    racine, globale, incr = lister_archives()
    motifs = [i for c in CODES for i in c["ids"]]
    articles, suppr = {}, set()
    debut = time.time()
    for nom in [globale] + incr:
        tmp = os.path.join(cache_dir, "legi.tar.gz")
        print(f"Codes : lecture de {nom}")
        try:
            if racine.startswith("file://"):
                tmp = racine[7:] + nom
            else:
                req = urllib.request.Request(racine + nom, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=1800) as r, open(tmp, "wb") as f:
                    while True:
                        b = r.read(1 << 20)
                        if not b:
                            break
                        f.write(b)
            k = parcourir(tmp, motifs, articles, suppr)
            print(f"  {k} versions d'articles retenues")
        finally:
            if not racine.startswith("file://") and os.path.exists(tmp):
                os.remove(tmp)
        if time.time() - debut > 2700:
            print("  temps dépassé : mises à jour suivantes ignorées pour ce passage")
            break
    for i in suppr:
        articles.pop(i, None)
    aujourd_hui = datetime.date.today().isoformat()
    os.makedirs(cache_codes, exist_ok=True)
    resume = []
    for c in CODES:
        mes = [a for a in articles.values() if a["_motif"] in c["ids"]]
        par_num = {}
        for a in mes:
            par_num.setdefault(a["num"], []).append(a)
        sortie, toc, toc_i = [], [], {}
        for num, versions in par_num.items():
            versions.sort(key=lambda a: a["debut"] or "")
            courantes = [a for a in versions if a["etat"] in EN_VIGUEUR]
            if not courantes:
                continue
            en_cours = [a for a in courantes if (a["debut"] or "") <= aujourd_hui] or courantes
            cur = en_cours[-1]
            avant = [a for a in versions if a is not cur and (a["fin"] or "") <= (cur["debut"] or "9999") and a["etat"] not in EN_VIGUEUR]
            prec = avant[-1] if avant else None
            chemin = []
            for t in cur["chemin"]:
                if t not in toc_i:
                    toc_i[t] = len(toc)
                    toc.append(t)
                chemin.append(toc_i[t])
            src = version_issue_de(cur)
            item = {"n": num, "id": cur["id"], "t": cur["texte"], "d": cur["debut"], "e": cur["etat"], "p": chemin,
                    "nv": len(versions)}
            if cur["nota"]:
                item["no"] = cur["nota"]
            if src:
                item["m"] = src["titre"]
                if src["cid"]:
                    item["mc"] = src["cid"]
            if prec and prec["texte"] and prec["texte"] != cur["texte"]:
                item["v"] = {"t": prec["texte"], "d": prec["debut"]}
            sortie.append(item)
        sortie.sort(key=lambda x: cle_num(x["n"]))
        if not sortie:
            print(f"  {c['titre']} : aucun article trouvé")
            continue
        doc = {"slug": c["slug"], "titre": c["titre"], "abr": c["abr"], "code": c["code"], "maj": aujourd_hui,
               "source": "DILA, base LEGI (Légifrance), Licence Ouverte", "toc": toc, "articles": sortie}
        nom = f"{c['slug']}.json"
        txt = json.dumps(doc, ensure_ascii=False, separators=(",", ":"))
        open(os.path.join(out_dir, nom), "w", encoding="utf-8").write(txt)
        open(os.path.join(cache_codes, nom), "w", encoding="utf-8").write(txt)
        resume.append({"slug": c["slug"], "titre": c["titre"], "abr": c["abr"], "n": len(sortie), "maj": aujourd_hui})
        print(f"  {c['titre']} : {len(sortie)} articles en vigueur ({len(txt) / 1e6:.1f} Mo)")
    idx = json.dumps({"maj": aujourd_hui, "codes": resume}, ensure_ascii=False)
    open(os.path.join(out_dir, "index.json"), "w", encoding="utf-8").write(idx)
    open(os.path.join(cache_codes, "index.json"), "w", encoding="utf-8").write(idx)
    json.dump({"date": datetime.datetime.now(datetime.timezone.utc).isoformat(), "globale": globale, "maj": len(incr)},
              open(etat_path, "w", encoding="utf-8"))


if __name__ == "__main__":
    racine = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    construire_codes(os.path.join(racine, "site"), os.path.join(racine, "cache"))
