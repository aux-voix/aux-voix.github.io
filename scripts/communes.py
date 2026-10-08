"""Table « commune → circonscription législative », pour trouver son député avec son code postal ou sa commune.

Sources officielles :
- résultats des élections législatives de 2024 par bureau de vote et par circonscription (ministère de l'Intérieur,
  data.gouv.fr, Licence Ouverte) : chaque bureau de vote est rattaché à sa circonscription en comparant la liste
  de ses candidats à celle de chaque circonscription (elle est unique dans un département) ;
- communes et codes postaux : API Découpage administratif (geo.api.gouv.fr, Etalab).
Le découpage des circonscriptions n'a pas changé depuis 2010 ; les fichiers de 2024 sont gardés en cache.
"""
import csv, io, json, os, re, time, urllib.request, datetime, gzip

R24 = "https://static.data.gouv.fr/resources/elections-legislatives-des-30-juin-et-7-juillet-2024-resultats-definitifs-du-1er-tour/"
SOURCES = {
    "bv": R24 + "20240710-171445/resultats-definitifs-par-bureau-de-vote.csv",
    "circ": R24 + "20240710-171413/resultats-definitifs-par-circonscriptions-legislatives.csv",
    "geo": "https://geo.api.gouv.fr/communes?fields=nom,code,codesPostaux,codeDepartement,population&format=json",
}
FICHIERS = {"bv": "legislatives-2024-bureaux.csv", "circ": "legislatives-2024-circonscriptions.csv", "geo": "communes-geo.json"}
DUREE = {"bv": None, "circ": None, "geo": 30}  # jours avant de recharger (None : jamais, le découpage est fixe)


def telecharger(cle, cache_dir):
    chemin = os.path.join(cache_dir, FICHIERS[cle])
    if os.path.exists(chemin) and os.path.getsize(chemin) > 1000:
        age = (time.time() - os.path.getmtime(chemin)) / 86400
        if DUREE[cle] is None or age < DUREE[cle]:
            return chemin
    derniere = None
    for essai in range(4):
        try:
            req = urllib.request.Request(SOURCES[cle], headers={"User-Agent": "AuxVoix/2.0 (reutilisation donnees ouvertes)", "Accept-Encoding": "gzip"})
            with urllib.request.urlopen(req, timeout=300) as r:
                brut = r.read()
                if (r.headers.get("Content-Encoding") or "").lower() == "gzip" or brut[:2] == b"\x1f\x8b":
                    brut = gzip.decompress(brut)
            if len(brut) < 1000:
                raise ValueError("fichier trop court")
            with open(chemin, "wb") as f:
                f.write(brut)
            return chemin
        except Exception as e:
            derniere = e
            time.sleep(3 * (essai + 1))
    if os.path.exists(chemin):
        print(f"Communes : {cle} indisponible ({derniere}), copie en cache utilisée")
        return chemin
    raise RuntimeError(f"{cle} indisponible ({derniere})")


def lire_csv(chemin):
    brut = open(chemin, "rb").read()
    try:
        texte = brut.decode("utf-8-sig")
    except UnicodeDecodeError:
        texte = brut.decode("latin-1")
    return list(csv.reader(io.StringIO(texte), delimiter=";"))


def candidats(ligne, entete):
    out, i = [], 1
    while f"Nom candidat {i}" in entete:
        k, p = entete.index(f"Nom candidat {i}"), entete.index(f"Prénom candidat {i}")
        nom = ligne[k].strip().upper() if k < len(ligne) else ""
        if nom:
            out.append((nom, ligne[p].strip().upper() if p < len(ligne) else ""))
        i += 1
    return tuple(sorted(out))


def dept_site(d):
    """Code de département tel qu'il figure dans les données des députés."""
    d = d.strip()
    if d == "ZZ":
        return "099"
    if d == "ZX":
        return "977"
    return d.zfill(2) if d.isdigit() and len(d) < 2 else d


def insee(code):
    code = code.strip()
    if code.startswith("ZX"):
        return "97" + code[2:]
    return code.zfill(5) if code.isdigit() else code


def table_2024(cache_dir):
    """Bureaux de vote et circonscriptions de 2024, réduits à une petite table gardée en cache (les fichiers bruts sont ensuite effacés)."""
    chemin = os.path.join(cache_dir, "table-communes-2024.json")
    if os.path.exists(chemin):
        try:
            T = json.load(open(chemin, encoding="utf-8"))
            if len(T) > 30000:
                return {k: {"nom": v[0], "dept": v[1], "circs": set(v[2]), "bv": [tuple(x) for x in v[3]]} for k, v in T.items()}
        except Exception:
            pass
    communes = rapprocher(cache_dir)
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump({k: [x["nom"], x["dept"], sorted(x["circs"]), sorted(set(x["bv"])) if len(x["circs"]) > 1 else []] for k, x in communes.items()}, f, ensure_ascii=False, separators=(",", ":"))
    for cle in ("bv", "circ"):
        try:
            os.remove(os.path.join(cache_dir, FICHIERS[cle]))
        except OSError:
            pass
    return communes


def rapprocher(cache_dir):
    C = lire_csv(telecharger("circ", cache_dir))
    B = lire_csv(telecharger("bv", cache_dir))
    hc, hb = C[0], B[0]
    i_dep, i_circ = hc.index("Code département"), hc.index("Code circonscription législative")
    index = {}
    for r in C[1:]:
        if len(r) <= i_circ:
            continue
        d = r[i_dep].strip()
        num = int(re.sub(r"\D", "", r[i_circ][len(d):]) or 0)
        index[(d, candidats(r, hc))] = (dept_site(d), num)
    b_dep, b_com, b_nom, b_bv = hb.index("Code département"), hb.index("Code commune"), hb.index("Libellé commune"), hb.index("Code BV")
    communes, perdus = {}, 0
    for r in B[1:]:
        if len(r) <= b_bv:
            continue
        cle = (r[b_dep].strip(), candidats(r, hb))
        c = index.get(cle)
        if not c:
            perdus += 1
            continue
        code = insee(r[b_com])
        x = communes.setdefault(code, {"nom": r[b_nom].strip(), "dept": c[0], "circs": set(), "bv": []})
        x["circs"].add(c[1])
        bv = re.sub(r"\D", "", r[b_bv]) or "0"
        x["bv"].append((int(bv), c[1]))
    if perdus > 50 or len(communes) < 30000:
        raise RuntimeError(f"rapprochement incomplet ({perdus} bureaux non reliés, {len(communes)} communes)")
    return communes


def construire_communes(site_dir, cache_dir):
    os.makedirs(cache_dir, exist_ok=True)
    sortie = os.path.join(site_dir, "communes.json")
    communes = table_2024(cache_dir)
    # communes actuelles et codes postaux
    try:
        geo = json.load(open(telecharger("geo", cache_dir), encoding="utf-8"))
    except Exception as e:
        print(f"Communes : codes postaux indisponibles ({e})")
        geo = []
    circs_dept = {}
    for x in communes.values():
        circs_dept.setdefault(x["dept"], set()).update(x["circs"])
    lignes, vus, sans = [], set(), 0
    for g in geo:
        code, dep = g.get("code", ""), g.get("codeDepartement", "")
        dep_s = "977" if dep in ("977", "978") else dept_site(dep)
        x = communes.get(code)
        if x is None and len(circs_dept.get(dep_s, ())) == 1:
            x = {"nom": g.get("nom", ""), "dept": dep_s, "circs": set(circs_dept[dep_s]), "bv": []}
        if x is None:
            sans += 1
            continue
        vus.add(code)
        lignes.append([g.get("nom") or x["nom"], code, " ".join(sorted(set(g.get("codesPostaux") or []))), x["dept"],
                       sorted(x["circs"])[0] if len(x["circs"]) == 1 else sorted(x["circs"]), int(g.get("population") or 0)])
    for code, x in communes.items():
        if code not in vus:
            lignes.append([x["nom"], code, "", x["dept"], sorted(x["circs"])[0] if len(x["circs"]) == 1 else sorted(x["circs"]), 0])
    bureaux = {}
    for code, x in communes.items():
        if len(x["circs"]) > 1:
            L = sorted(set(x["bv"]))
            bureaux[code] = [[b, c] for b, c in L]
    lignes.sort(key=lambda l: (l[3], l[1]))
    doc = {"maj": datetime.date.today().isoformat(),
           "sources": ["Ministère de l'Intérieur, résultats des élections législatives de 2024 par bureau de vote (data.gouv.fr, Licence Ouverte)",
                       "Etalab, API Découpage administratif (geo.api.gouv.fr), communes et codes postaux"],
           "c": lignes, "b": bureaux}
    with open(sortie, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
    print(f"Communes : {len(lignes)} communes reliées à leur circonscription ({len(bureaux)} partagées entre plusieurs), "
          f"{sans} communes récentes sans correspondance, {os.path.getsize(sortie) // 1024} Ko")
