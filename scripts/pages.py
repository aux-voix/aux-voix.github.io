#!/usr/bin/env python3
"""Le Relevé : pages statiques lisibles par les moteurs de recherche (députés, votes, lois, articles de code),
plan du site, robots.txt et flux RSS. Un seul interrupteur, "public" dans contenu/site.json, ouvre le site à
l'indexation ; tant qu'il vaut false, chaque page porte noindex et robots.txt interdit l'exploration."""
import datetime, html, json, os, re, statistics
from email.utils import format_datetime

MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
ESC = lambda s: html.escape(str(s if s is not None else ""), quote=True)


def fd(iso):
    if not iso:
        return ""
    a, m, j = int(iso[:4]), int(iso[5:7]), int(iso[8:10])
    return f"{'1er' if j == 1 else j} {MOIS[m - 1]} {a}"


def ordinal(k):
    return "1re" if k == 1 else f"{k}e"


def pc(x):
    return "—" if x is None else f"{round(x * 100)}\u00a0%"


def slug_num(n):
    return re.sub(r"[^A-Za-z0-9-]+", "-", n.replace(".", "")).strip("-") or "0"


def mediane(v):
    v = [x for x in v if x is not None]
    return statistics.median(v) if v else None


CSS = """@font-face{font-family:"Lexend";src:url("/fonts/Lexend.ttf") format("truetype");font-weight:300 800;font-display:swap}
@font-face{font-family:"Source Sans 3";src:url("/fonts/SourceSans3.ttf") format("truetype");font-weight:200 900;font-display:swap}
:root{--t:#1B1D1F;--t2:#5A6169;--b:#DDE1E5;--b2:#EDF0F3;--g:#F5F7F9;--bl:#123B6D;--bl2:#1B58A3;--blc:#EAF0F7;--pour:#1F6FB2;--contre:#C2690A;--abst:#8A9099}
*{box-sizing:border-box}body{margin:0;font:400 16.5px/1.6 "Source Sans 3",Helvetica,Arial,sans-serif;color:var(--t);background:#fff}
a{color:var(--bl2);text-underline-offset:.18em}h1,h2,h3{font-family:"Lexend","Source Sans 3",Arial,sans-serif;font-weight:600;letter-spacing:-.015em;line-height:1.22;margin:0}
.w{max-width:900px;margin:0 auto;padding:0 20px}.beta{background:var(--blc);border-bottom:1px solid #D2DFEC;font-size:14px;padding:8px 0}
header{border-bottom:1px solid var(--b)}header .w{display:flex;flex-wrap:wrap;gap:8px 22px;align-items:center;min-height:62px}
.logo{font:800 20px "Lexend",Arial,sans-serif;color:var(--t);text-decoration:none}.logo:after{content:"";display:block;width:24px;height:3px;background:var(--bl2);margin-top:3px}
nav a{font-weight:600;color:var(--t);text-decoration:none;margin-right:16px;font-size:15px}nav a:hover{color:var(--bl2)}
main{padding:30px 0 50px}.fil{font-size:14px;color:var(--t2);margin:0 0 6px}h1{font-size:clamp(24px,3.4vw,32px);margin-bottom:10px}
h2{font-size:20px;margin:30px 0 10px;padding-bottom:8px;border-bottom:2px solid var(--t)}.lede{font-size:18px;color:var(--t2);margin:0 0 14px}
.cta{display:inline-block;background:var(--bl);color:#fff;text-decoration:none;font-weight:600;padding:10px 16px;margin:8px 10px 8px 0}.cta:hover{background:var(--bl2)}
.cta.s{background:#fff;color:var(--t);border:1px solid var(--b)}dl{display:grid;grid-template-columns:max-content 1fr;gap:6px 18px;margin:12px 0}dt{color:var(--t2)}dd{margin:0}
table{border-collapse:collapse;width:100%;font-size:15px}th{text-align:left;border-bottom:2px solid var(--t);padding:8px 10px 8px 0;font-size:14px}td{border-bottom:1px solid var(--b2);padding:9px 10px 9px 0;vertical-align:top}
.v{font-weight:600;white-space:nowrap}.v:before{content:"";display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px;background:var(--c,var(--abst))}
.v1{--c:var(--pour)}.v2{--c:var(--contre)}.v3{--c:var(--abst)}.art{border-left:4px solid var(--bl);background:var(--g);padding:16px 20px;font-size:18px;line-height:1.65;margin:16px 0}
.art p{margin:0 0 .6em}.cite{border:1px solid var(--b);padding:12px 16px;margin:18px 0;font-size:15px}.cite p{margin:0 0 6px}.cite button{font:600 14px inherit;padding:6px 10px;border:1px solid var(--b);background:#fff;cursor:pointer;margin-right:6px}
.cite button:hover{border-color:var(--bl2);color:var(--bl2)}.meta{font-size:14px;color:var(--t2)}.noms{font-size:14.5px;line-height:1.7}ul.l{padding-left:1.1em}
footer{border-top:1px solid var(--b);background:var(--g);font-size:14px;color:var(--t2);padding:22px 0}footer a{margin-right:14px}
.tw{overflow-x:auto;margin:0 0 8px}.cite span,.art,.lede,dd{overflow-wrap:anywhere}
@media(max-width:600px){dl{grid-template-columns:1fr;gap:2px}dd{margin-bottom:8px}table{font-size:14px}}"""

JS = """document.addEventListener("click",function(e){var b=e.target.closest("[data-copie]");if(!b)return;var t=document.getElementById(b.getAttribute("data-copie")).textContent;
function ok(){var x=b.textContent;b.textContent="Copié";setTimeout(function(){b.textContent=x;},1500);}
if(navigator.clipboard&&window.isSecureContext){navigator.clipboard.writeText(t).then(ok);}else{var a=document.createElement("textarea");a.value=t;document.body.appendChild(a);a.select();try{document.execCommand("copy");ok();}catch(_){}a.remove();}});"""


class Generateur:
    def __init__(self, site_dir):
        self.site = site_dir
        cfg = {}
        try:
            cfg = json.load(open(os.path.join(site_dir, "contenu", "site.json"), encoding="utf-8"))
        except Exception:
            pass
        self.public = bool(cfg.get("public"))
        self.url = (cfg.get("url") or "https://lereleve.github.io").rstrip("/")
        self.urls = {"deputes": [], "votes": [], "lois": [], "codes": []}
        self.deputes_faits = set()   # un député élu sous plusieurs législatures garde la page de la plus récente
        self.aujourdhui = datetime.date.today().isoformat()

    def page(self, chemin, titre, description, corps, canonique=True, rss=None):
        robots = "" if self.public else '<meta name="robots" content="noindex, nofollow">\n'
        alt = f'<link rel="alternate" type="application/rss+xml" title="{ESC(rss[1])}" href="{ESC(rss[0])}">\n' if rss else ""
        doc = f"""<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{ESC(titre)} | Le Relevé</title><meta name="description" content="{ESC(description[:300])}">
{robots}<link rel="canonical" href="{ESC(self.url + chemin)}">{alt}<link rel="stylesheet" href="/statique.css"></head><body>
{'' if self.public else '<div class="beta"><div class="w">Version bêta du site.</div></div>'}
<header><div class="w"><a class="logo" href="/">Le Relevé</a><nav aria-label="Rubriques"><a href="/#/lois">Lois</a><a href="/#/codes">Codes</a><a href="/#/elus">Élus</a><a href="/#/votes">Votes</a><a href="/#/methode">Méthode</a></nav></div></header>
<main id="main"><div class="w">{corps}</div></main>
<footer><div class="w"><p>Données officielles de l'Assemblée nationale et de la DILA (Légifrance), sous Licence Ouverte, mises à jour le {fd(self.aujourdhui)}.</p>
<p><a href="/#/methode/sources">Sources</a><a href="/#/methode/mentions">Mentions légales</a><a href="/#/methode/accessibilite">Accessibilité</a><a href="/flux/">Flux de suivi</a></p></div></footer>
<script src="/statique.js" defer></script></body></html>"""
        doc = doc.replace("<table>", '<div class="tw"><table>').replace("</table>", "</table></div>")
        dest = os.path.join(self.site, chemin.strip("/"), "index.html")
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        open(dest, "w", encoding="utf-8").write(doc)
        return chemin

    def bloc_citer(self, ident, lignes):
        out = '<div class="cite" aria-label="Citer cette page"><h3 style="font-size:16px;margin:0 0 8px">Citer cette page</h3>'
        for i, (lib, txt) in enumerate(lignes):
            out += f'<p><span class="meta">{ESC(lib)}</span><br><span id="{ident}-{i}">{ESC(txt)}</span> <button type="button" data-copie="{ident}-{i}">Copier</button></p>'
        return out + "</div>"

    # ---------------- législatures ----------------
    def legislature(self, d, courante):
        leg = d["legislature"]
        grp = d["groupes"]
        deps = d["deputes"]
        K = len(d["periodes"])
        G = lambda i: grp[i] if 0 <= i < len(grp) else {"sigle": "?", "nom": "Groupe inconnu", "ni": True}
        # médianes de groupe et de commission, pour mettre chaque chiffre en contexte
        par_g, par_c = {}, {}
        for x in deps:
            if not x["actif"] or x["st"][K]["el"] < 20:
                continue
            par_g.setdefault(x["groupe"], []).append(x["st"][K])
            if x.get("commission"):
                par_c.setdefault(x["commission"], []).append(x["st"][K])
        med = lambda L, c: mediane([s[c] for s in L])
        scr = d["scrutins"]
        idx_dep = {x["id"]: i for i, x in enumerate(deps)}
        retenus = [s for s in scr if s["t"] in ("SPS", "MOC") or re.match(r"l.ensemble", s["ti"], re.I)]
        num_retenus = {s["n"] for s in retenus}
        def lien_vote(n):
            return f"/vote/{leg}/{n}/" if n in num_retenus else f"/#/scrutin/{n}"
        # --- députés ---
        for i, x in enumerate(deps):
            if x["id"] in self.deputes_faits:
                continue
            self.deputes_faits.add(x["id"])
            nom = f"{x['prenom']} {x['nom']}".strip()
            g = G(x["groupe"])
            fem = x.get("civ") == "Mme"
            qual = "Députée" if fem else "Député"
            lieu = f"{x['dept']} ({x['numDept']}), {ordinal(x['circ'])} circonscription" if x.get("dept") else "circonscription non renseignée"
            st = x["st"][K]
            mg = par_g.get(x["groupe"], [])
            mc = par_c.get(x.get("commission"), [])
            lignes_ind = ""
            for lib, c in (("Participation aux scrutins solennels", "partS"), ("Participation à tous les scrutins publics", "part"), ("Vote comme son groupe", "align")):
                if c == "align" and g.get("ni"):
                    continue
                lignes_ind += f"<tr><td>{lib}</td><td><strong>{pc(st[c])}</strong></td><td>{pc(med(mg, c))}</td><td>{pc(med(mc, c)) if mc else '—'}</td><td>{pc(d['medianes'][K][c])}</td></tr>"
            votes = []
            for s in reversed(retenus):
                c = s["v"][i] if i < len(s["v"]) else "-"
                if c in "123":
                    votes.append(s)
                    if len(votes) >= 12:
                        break
            vl = {"1": "Pour", "2": "Contre", "3": "Abstention", "4": "Non-votant", "0": "N'a pas pris part"}
            tv = "".join(f'<tr><td class="meta">{fd(s["d"])}</td><td><a href="{lien_vote(s["n"])}">{ESC(s["ti"][:1].upper() + s["ti"][1:])}</a></td><td><span class="v v{s["v"][i]}">{vl[s["v"][i]]}</span></td></tr>' for s in votes)
            am = x.get("am")
            chemin = f"/depute/{x['id']}/"
            cit = [("Référence", f"{nom}, {qual.lower()}{(' (' + x['dept'] + ', ' + ordinal(x['circ']) + ' circonscription)') if x.get('dept') else ''}, groupe {g['nom']}, {d['label']}, Assemblée nationale."),
                   ("Avec la source", f"Le Relevé, fiche de {nom}, d'après les données de l'Assemblée nationale, {self.url}{chemin} (consulté le {fd(self.aujourdhui)}).")]
            corps = f"""<p class="fil"><a href="/#/elus">Élus</a>, {ESC(d['label'])}</p><h1>{ESC(nom)}</h1>
<p class="lede">{qual}{'' if x['actif'] else ' (mandat terminé)'}, {ESC(lieu)}. Groupe : {ESC(g['nom'])} ({ESC(g['sigle'])}).</p>
<a class="cta" href="/#/elu/{x['id']}">Ouvrir la fiche complète</a><a class="cta s" href="https://www.assemblee-nationale.fr/dyn/deputes/{x['id']}">Fiche officielle à l'Assemblée</a>
<dl><dt>Parti de rattachement</dt><dd>{ESC(x.get('parti') or 'Aucun déclaré')}</dd><dt>Commission</dt><dd>{ESC(x.get('commission') or '—')}</dd><dt>Mandat</dt><dd>Depuis le {fd(x.get('debut'))}</dd>
{f"<dt>Amendements</dt><dd>{am[0]} déposés en premier signataire, dont {am[1]} adoptés ; {am[2]} cosignés</dd>" if am else ""}</dl>
<h2>Participation aux votes, en contexte</h2><p class="meta">L'Assemblée ne publie pas de relevé de présence : ces chiffres mesurent la participation aux votes publics, comparée à la médiane de son groupe, de sa commission et de l'ensemble des députés.</p>
<table><thead><tr><th>Indicateur</th><th>{ESC(nom)}</th><th>Son groupe</th><th>Sa commission</th><th>Assemblée</th></tr></thead><tbody>{lignes_ind}</tbody></table>
{f"<h2>Ses derniers votes importants</h2><table><thead><tr><th>Date</th><th>Scrutin</th><th>Son vote</th></tr></thead><tbody>{tv}</tbody></table>" if tv else ""}
{self.bloc_citer("c", cit)}<p class="meta"><a href="/flux/depute/{x['id']}.xml">Suivre ses votes (flux RSS)</a></p>"""
            self.page(chemin, f"{nom}, {qual.lower()} : votes et participation", f"{nom}, {qual.lower()} {lieu}, groupe {g['nom']} : ses votes, sa participation et ses amendements, d'après les données officielles de l'Assemblée nationale.",
                      corps, rss=(f"/flux/depute/{x['id']}.xml", f"Votes de {nom}"))
            self.urls["deputes"].append((chemin, d["maj"][:10]))
            if courante:
                self.flux(f"/flux/depute/{x['id']}.xml", f"Le Relevé, votes de {nom}", f"Les derniers votes de {nom} à l'Assemblée nationale.",
                          [(f"{s['ti'][:1].upper() + s['ti'][1:]} : {vl[s['v'][i]].lower()}", self.url + lien_vote(s["n"]) if s["n"] in num_retenus else f"{self.url}/#/scrutin/{s['n']}", s["d"],
                            f"Vote de {nom} : {vl[s['v'][i]].lower()}. Résultat : {'adopté' if 'adopt' in s['so'] else 'rejeté'}, {s['po']} pour, {s['co']} contre.") for s in votes])
        # --- votes importants ---
        lois_par_scr = {}
        for l in d.get("lois", []):
            for k in l.get("scrutins", []):
                lois_par_scr[k] = l
        for s in retenus:
            adopte = "adopt" in s["so"]
            moc = s["t"] == "MOC"
            ti = s["ti"][:1].upper() + s["ti"][1:]
            titre = f"Motion de censure {'adoptée' if adopte else 'rejetée'} : {s['po']} voix" if moc else f"{'Adopté' if adopte else 'Rejeté'} : {ti}"
            pos = {1: [], 2: [], 3: []}
            for b in s["g"]:
                gg = G(b[0])
                if not gg.get("ni") and b[2] in pos:
                    pos[b[2]].append(gg["sigle"])
            noms = {"1": [], "2": [], "3": []}
            for i, x in enumerate(deps):
                c = s["v"][i] if i < len(s["v"]) else "-"
                if c in noms:
                    noms[c].append(f'<a href="/depute/{x["id"]}/">{ESC(x["prenom"] + " " + x["nom"])}</a>')
            l = lois_par_scr.get(s["n"])
            chemin = f"/vote/{leg}/{s['n']}/"
            cit = [("Référence", f"Assemblée nationale, scrutin public n° {s['n']} du {fd(s['d'])}, sur {s['ti']}."),
                   ("Avec la source", f"Le Relevé, d'après les données de l'Assemblée nationale, {self.url}{chemin} (consulté le {fd(self.aujourdhui)}).")]
            corps = f"""<p class="fil"><a href="/#/votes">Votes</a>, {ESC(d['label'])}, scrutin n° {s['n']}</p><h1>{ESC(titre)}</h1>
<p class="lede">Le {fd(s['d'])}, l'Assemblée a {'adopté' if adopte else 'rejeté'} {ESC(s['ti'])}{'' if moc else f", par {s['po']} voix pour et {s['co']} contre ({s['ab']} abstentions)"}.</p>
<a class="cta" href="/#/scrutin/{s['n']}">Voir l'hémicycle et les explications</a><a class="cta s" href="https://www.assemblee-nationale.fr/dyn/{leg}/scrutins/{s['n']}">Scrutin sur le site de l'Assemblée</a>
{f'<p>Texte concerné : <a href="/loi/{ESC(l["id"])}/">{ESC(l["titre"][:1].upper() + l["titre"][1:])}</a></p>' if l else ''}
<h2>Les groupes</h2><ul class="l"><li>Majoritairement pour : {', '.join(pos[1]) or 'aucun'}</li><li>Majoritairement contre : {', '.join(pos[2]) or 'aucun'}</li><li>Majoritairement abstention : {', '.join(pos[3]) or 'aucun'}</li></ul>
<h2>Le vote de chaque député</h2><p class="noms"><span class="v v1">Pour ({len(noms['1'])})</span> {', '.join(noms['1']) or '—'}</p><p class="noms"><span class="v v2">Contre ({len(noms['2'])})</span> {', '.join(noms['2']) or '—'}</p><p class="noms"><span class="v v3">Abstention ({len(noms['3'])})</span> {', '.join(noms['3']) or '—'}</p>
{self.bloc_citer("c", cit)}"""
            self.page(chemin, titre[:110], f"Scrutin public n° {s['n']} du {fd(s['d'])} à l'Assemblée nationale : {s['ti'][:160]}. Résultat et vote de chaque député.", corps)
            self.urls["votes"].append((chemin, s["d"]))
        if courante:
            self.flux("/flux/votes.xml", "Le Relevé, votes importants", "Les votes solennels, motions de censure et votes sur l'ensemble des textes à l'Assemblée nationale.",
                      [(f"{'Adopté' if 'adopt' in s['so'] else 'Rejeté'} : {s['ti'][:1].upper() + s['ti'][1:]}", f"{self.url}/vote/{leg}/{s['n']}/", s["d"],
                        f"{s['po']} pour, {s['co']} contre, {s['ab']} abstentions.") for s in list(reversed(retenus))[:50]])
        # --- lois ---
        evenements = []
        for l in d.get("lois", []):
            E = l.get("etapes") or []
            chemin = f"/loi/{l['id']}/"
            titre = l["titre"][:1].upper() + l["titre"][1:]
            etapes = "".join(f"<tr><td class='meta'>{fd(e[2])}</td><td>{ESC(libelle_etape(e, E))}</td><td>{ESC((e[3] if len(e) > 3 else '') or '')}</td></tr>" for e in E if i_utile(e, E))
            prom = l.get("prom")
            statut = f"Promulguée le {fd(prom['date'])}" if prom else (f"En cours : {libelle_etape(E[-1], E).lower()} le {fd(E[-1][2])}" if E else "En cours")
            fin = [scr_n for scr_n in l.get("scrutins", []) if scr_n in num_retenus]
            cit = [("Référence", ((prom or {}).get("titre") or titre) + (f", JO du {fd(prom['date'])}" if prom else f" ({d['label']}, dossier législatif de l'Assemblée nationale)")),
                   ("Avec la source", f"Le Relevé, d'après les données de l'Assemblée nationale, {self.url}{chemin} (consulté le {fd(self.aujourdhui)}).")]
            corps = f"""<p class="fil"><a href="/#/lois">Lois</a>, {ESC(d['label'])}</p><h1>{ESC(titre)}</h1><p class="lede">{ESC(statut)}.</p>
<a class="cta" href="/#/loi/{ESC(l['id'])}">Voir le parcours et les votes</a>{f'<a class="cta s" href="{ESC(prom["url"])}">Texte sur Légifrance</a>' if prom and prom.get("url") else ''}
{f'<h2>Son parcours</h2><table><thead><tr><th>Date</th><th>Étape</th><th>Résultat</th></tr></thead><tbody>{etapes}</tbody></table>' if etapes else ''}
{f'<h2>Votes à l’Assemblée</h2><ul class="l">' + ''.join(f'<li><a href="/vote/{leg}/{k}/">Scrutin n° {k}</a></li>' for k in fin) + '</ul>' if fin else ''}
{self.bloc_citer("c", cit)}"""
            self.page(chemin, titre[:110], f"{titre[:200]} : parcours au Parlement, votes et statut. {statut}.", corps)
            self.urls["lois"].append((chemin, (prom or {}).get("date") or (E[-1][2] if E else d["maj"][:10])))
            if E:
                evenements.append((E[-1][2], titre, chemin, statut))
        if courante:
            evenements.sort(reverse=True)
            self.flux("/flux/lois.xml", "Le Relevé, lois", "Les dernières étapes franchies par les textes de loi au Parlement.",
                      [(t, self.url + c, dt, st) for dt, t, c, st in evenements[:50]])

    # ---------------- codes ----------------
    def codes(self):
        dossier = os.path.join(self.site, "codes")
        try:
            ix = json.load(open(os.path.join(dossier, "index.json"), encoding="utf-8"))
        except Exception:
            return
        limite = (datetime.date.today() - datetime.timedelta(days=365)).isoformat()
        for c in ix.get("codes", []):
            try:
                code = json.load(open(os.path.join(dossier, c["slug"] + ".json"), encoding="utf-8"))
            except Exception:
                continue
            nom_code = f"du {code['titre']}" if code["code"] else f"de la {code['titre']}"
            recents = []
            for a in code["articles"]:
                num = a["n"]
                chemin = f"/code/{code['slug']}/{slug_num(num)}/"
                art_l = num if re.match(r"^\d", num) else re.sub(r"^([A-Z]+)\.?\s*", r"\1. ", num)
                url_lf = f"https://www.legifrance.gouv.fr/{'codes' if code['code'] else 'loda'}/article_lc/{a['id']}"
                src = re.sub(r"\s*-\s*art\..*$", "", a.get("m") or "")
                paras = "".join(f"<p>{ESC(p).replace(chr(10), '<br>')}</p>" for p in a["t"].split("\n\n"))
                fil = " / ".join(ESC(code["toc"][k]) for k in a.get("p", []))
                cit = [("Référence", f"{code['abr']}, art. {art_l}"),
                       ("Dans une phrase", f"Article {art_l} {nom_code}" + (f", dans sa rédaction issue de {src[:1].lower() + src[1:]}" if src else "") + "."),
                       ("Note de bas de page", f"{code['abr']}, art. {art_l} ; Légifrance, {url_lf}, consulté le {fd(self.aujourdhui)}.")]
                prec = a.get("v")
                corps = f"""<p class="fil"><a href="/#/codes">Codes</a>, <a href="/#/code/{code['slug']}">{ESC(code['titre'])}</a></p>{f'<p class="meta">{fil}</p>' if fil else ''}
<h1>Article {ESC(art_l)} {ESC(nom_code)}</h1><p class="lede">En vigueur depuis le {fd(a['d'])}{', issu de ' + ESC(src[:1].lower() + src[1:]) if src else ''}.</p>
<blockquote class="art">{paras}</blockquote>
<a class="cta" href="/#/code/{code['slug']}/{ESC(num)}">Voir ce qui a changé et les articles voisins</a><a class="cta s" href="{ESC(url_lf)}">Lire sur Légifrance</a>
{self.bloc_citer("c", cit)}
{f'<h2>Version précédente</h2><p class="meta">En vigueur du {fd(prec["d"])} au {fd(a["d"])}.</p><blockquote class="art" style="border-left-color:var(--abst);font-size:16px">' + ''.join(f"<p>{ESC(p)}</p>" for p in prec["t"].split(chr(10) + chr(10))) + '</blockquote>' if prec else ''}
<p class="meta">Texte : DILA, base LEGI (Légifrance), Licence Ouverte. Seule la publication au Journal officiel fait foi.</p>"""
                self.page(chemin, f"Article {art_l} {nom_code}", f"Article {art_l} {nom_code}, version en vigueur : {a['t'][:200]}", corps,
                          rss=(f"/flux/code/{code['slug']}.xml", f"Modifications du {code['titre']}"))
                self.urls["codes"].append((chemin, a["d"] if a["d"] and a["d"] < "2900" else self.aujourdhui))
                if a["d"] and limite <= a["d"] <= self.aujourdhui:
                    recents.append((a["d"], art_l, chemin, src))
            recents.sort(reverse=True)
            self.flux(f"/flux/code/{code['slug']}.xml", f"Le Relevé, modifications du {code['titre']}", f"Les articles du {code['titre']} modifiés au cours des douze derniers mois.",
                      [(f"Article {n} modifié", self.url + ch, dt, f"Nouvelle rédaction en vigueur le {fd(dt)}" + (f", issue de {s[:1].lower() + s[1:]}" if s else "") + ".") for dt, n, ch, s in recents[:100]])

    # ---------------- flux, plan du site, robots ----------------
    def flux(self, chemin, titre, desc, items):
        def rfc(iso):
            try:
                return format_datetime(datetime.datetime.fromisoformat(iso[:10] + "T12:00:00+00:00"))
            except Exception:
                return ""
        it = "".join(f"<item><title>{ESC(t)}</title><link>{ESC(u)}</link><guid>{ESC(u)}#{ESC(dt)}</guid><pubDate>{rfc(dt)}</pubDate><description>{ESC(dd)}</description></item>" for t, u, dt, dd in items)
        xml = f'<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel><title>{ESC(titre)}</title><link>{ESC(self.url)}</link><description>{ESC(desc)}</description><language>fr</language>{it}</channel></rss>'
        dest = os.path.join(self.site, chemin.strip("/"))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        open(dest, "w", encoding="utf-8").write(xml)

    def finaliser(self):
        open(os.path.join(self.site, "statique.css"), "w", encoding="utf-8").write(CSS)
        open(os.path.join(self.site, "statique.js"), "w", encoding="utf-8").write(JS)
        cartes = []
        for nom, L in self.urls.items():
            if not L:
                continue
            for k in range(0, len(L), 45000):
                fichier = f"sitemap-{nom}-{k // 45000 + 1}.xml"
                corps = "".join(f"<url><loc>{ESC(self.url + c)}</loc><lastmod>{ESC((dt or self.aujourdhui)[:10])}</lastmod></url>" for c, dt in L[k:k + 45000])
                open(os.path.join(self.site, fichier), "w", encoding="utf-8").write(f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{corps}</urlset>')
                cartes.append(fichier)
        index = "".join(f"<sitemap><loc>{ESC(self.url)}/{f}</loc><lastmod>{self.aujourdhui}</lastmod></sitemap>" for f in cartes)
        open(os.path.join(self.site, "sitemap.xml"), "w", encoding="utf-8").write(f'<?xml version="1.0" encoding="UTF-8"?>\n<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{index}</sitemapindex>')
        robots = f"User-agent: *\nAllow: /\nSitemap: {self.url}/sitemap.xml\n" if self.public else "# Site en version bêta : exploration désactivée jusqu'à l'ouverture publique.\nUser-agent: *\nDisallow: /\n"
        open(os.path.join(self.site, "robots.txt"), "w", encoding="utf-8").write(robots)
        # page d'accueil des flux
        liens = "".join(f'<li><a href="/flux/{f}">{t}</a></li>' for f, t in (("votes.xml", "Votes importants de l'Assemblée"), ("lois.xml", "Étapes des lois")))
        self.page("/flux/", "Flux de suivi", "Suivre les votes, les lois et les modifications des codes avec un lecteur de flux RSS.",
                  f"<h1>Flux de suivi</h1><p class='lede'>Ajoutez ces adresses à un lecteur de flux (Feedly, Thunderbird, NetNewsWire…) pour être prévenu automatiquement. Chaque fiche de député et chaque code a aussi son propre flux.</p><ul class='l'>{liens}</ul>")
        # l'interrupteur s'applique aussi à la page principale du site
        idx = os.path.join(self.site, "index.html")
        if self.public and os.path.exists(idx):
            s = open(idx, encoding="utf-8").read()
            s = re.sub(r'\s*<!-- Version bêta[^>]*-->\s*<meta name="robots" content="noindex, nofollow">', "", s)
            s = s.replace('<meta name="robots" content="noindex, nofollow">', "")
            open(idx, "w", encoding="utf-8").write(s)
        total = sum(len(v) for v in self.urls.values())
        print(f"Pages publiques : {total} ({', '.join(f'{k} {len(v)}' for k, v in self.urls.items())}) ; indexation {'ouverte' if self.public else 'fermée (version bêta)'}")


def chambre(c):
    return "AN" if re.match(r"^AN|^CMP-DEBATS-AN", c) else "SN" if re.match(r"^SN|^CMP-DEBATS-SN", c) else None


def lecture(c):
    for m, l in ((r"^(AN|SN)1-", "première lecture"), (r"^(AN|SN)2-", "deuxième lecture"), (r"NLEC", "nouvelle lecture"), (r"LDEF", "lecture définitive"), (r"LUNI", "lecture unique")):
        if re.search(m, c):
            return l
    return None


def i_utile(e, E):
    return E.index(e) == 0 or "DEPOT" not in e[0]


def libelle_etape(e, E):
    c, ch, lec = e[0], chambre(e[0]), lecture(e[0])
    lieu = {"AN": "à l'Assemblée", "SN": "au Sénat"}.get(ch, "")
    if c.startswith("PROM"):
        return "Promulgation"
    if c.startswith("CC"):
        return "Décision du Conseil constitutionnel"
    if c.startswith("CMP-DEC"):
        return "Conclusion de la commission mixte paritaire"
    if c.startswith("CMP-DEPOT"):
        return "Commission mixte paritaire convoquée"
    if c.startswith("CMP-DEBATS"):
        return f"Vote du texte de compromis {lieu}".strip()
    if "DEPOT" in c:
        return f"Dépôt {lieu}".strip() if E.index(e) == 0 else f"Transmission {lieu}".strip()
    if c.endswith("DEC"):
        return f"Vote en {lec or 'séance'} {lieu}".strip()
    return (e[1] or c)[:1].upper() + (e[1] or c)[1:]


def generer(site_dir):
    g = Generateur(site_dir)
    try:
        ix = json.load(open(os.path.join(site_dir, "index.json"), encoding="utf-8"))
    except Exception:
        ix = {"legislatures": []}
    for L in sorted(ix.get("legislatures", []), key=lambda x: (x.get("au") is not None, -(int(x.get("leg", 0) or 0)))):
        try:
            d = json.load(open(os.path.join(site_dir, L["fichier"]), encoding="utf-8"))
            g.legislature(d, d.get("courante", False))
        except Exception as e:
            print(f"Pages : {L.get('label')} ignorée ({e})")
    g.codes()
    g.finaliser()


if __name__ == "__main__":
    racine = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    generer(os.path.join(racine, "site"))
