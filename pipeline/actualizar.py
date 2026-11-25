#!/usr/bin/env python3
"""Actualización automática de la web de golfistas españolas.

Fuentes (todas públicas):
  - Clippd Scoreboard (NCAA): torneos de cada jugadora, futuros incluidos, y clasificación hoyo a hoyo.
  - Ladies European Tour (servicio de datos OCS): clasificación y horarios de salida.
  - WAGR: puesto de esta semana de todas las españolas.
  - RFEG (livegolfscoring / mitarjeta.golf): clasificaciones de los torneos apuntados en fuentes.json.

Escribe site/auto.js, que la web mezcla con sus datos al cargar. No toca index.html.
Si una fuente falla, conserva lo que había, lo apunta en «errores» y sigue con las demás.

Uso: python3 pipeline/actualizar.py [--temporada] [--prueba]
  --temporada  repasa la NCAA desde agosto (para rellenar huecos; tarda más)
  --prueba     no escribe nada, solo enseña lo que haría
"""
import html, json, os, re, sys, time, unicodedata, urllib.parse, urllib.request
from datetime import datetime, date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
SITE, PIPE = ROOT / "site", ROOT / "pipeline"
TZ = ZoneInfo("Europe/Madrid")
MES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36",
      "Accept-Language": "es-ES,es;q=0.9,en;q=0.8"}
CLIPPD = "https://scoreboard.clippd.com"
NOW = datetime.now(TZ)
TODAY = NOW.date()
ARGS = set(sys.argv[1:])
LOG = []


def log(*a):
    s = " ".join(str(x) for x in a)
    LOG.append(s)
    print(s, flush=True)


# ---------------------------------------------------------------- utilidades

def norm(s):
    s = unicodedata.normalize("NFD", html.unescape(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z ]+", " ", s).split()


def same_person(full_name, other):
    """Nombre y al menos un apellido iguales. Acepta «Apellido, Nombre» y «Nombre Apellido (ESP)»."""
    other = re.sub(r"\(.*?\)", "", other or "")
    if "," in other:
        sur, first = other.split(",", 1)
        other = first + " " + sur
    a, b = norm(full_name), norm(other)
    if len(a) < 2 or len(b) < 2 or a[0] != b[0]:
        return False
    # El primer apellido de una tiene que estar en el nombre de la otra (evita confundir «Daniela Campillo
    # Martínez» con «Daniela Carrión Martínez» por compartir el segundo apellido).
    return a[1] in b[1:] or b[1] in a[1:]


def fetch(url, tries=3):
    last = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=45) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:  # reintenta errores de red pasajeros
            last = e
            time.sleep(3 * (i + 1))
    raise last


def fetch_json(url):
    return json.loads(fetch(url))


def d(s):
    return date.fromisoformat(s[:10])


def tp_from(s):
    s = str(s).strip().replace("−", "-")
    if s.upper() in ("E", "PAR", "0"):
        return 0
    return int(s) if re.fullmatch(r"[+-]?\d+", s) else None


def ties(rows, key="rank"):
    """Añade «T» al puesto cuando lo comparten varias."""
    cnt = {}
    for r in rows:
        if r.get(key):
            cnt[r[key]] = cnt.get(r[key], 0) + 1
    for r in rows:
        k = r.get(key)
        r["pos"] = ("T" if k and cnt.get(k, 0) > 1 else "") + str(k) if k else "—"


# ---------------------------------------------------------- datos de la web

def site_data():
    """Lee de index.html las jugadoras, los calendarios de cada universidad y los torneos nacionales."""
    t = (SITE / "index.html").read_text(encoding="utf-8")
    nac0 = t.index("const NAC_P=")
    pls = []
    for m in re.finditer(r'\{\s*"?id"?\s*:\s*"([a-z0-9]+)"\s*,\s*"?n"?\s*:\s*"([^"]+)"\s*,\s*"?(?:u|fed)"?\s*:\s*"([^"]*)"', t):
        mode = "nac" if m.start() > nac0 else "ncaa"
        pls.append({"id": m.group(1), "n": m.group(2), "u": m.group(3) if mode == "ncaa" else None, "mode": mode})
    sched = {}
    s0 = t.index("let S = {")
    s1 = t.index("};", s0)
    for m in re.finditer(r"\n\s*([a-z0-9]+):\[(.*)", t[s0:s1]):
        uni, body = m.group(1), m.group(2)
        sched[uni] = [{"id": e[0], "n": e[1], "a": e[2], "b": e[3] or e[2]}
                      for e in re.findall(r'E\("([^"]+)","([^"]*)","(\d{4}-\d\d-\d\d)","(\d{4}-\d\d-\d\d)?"', body)]
    return pls, sched


# ------------------------------------------------------------- Clippd / NCAA

def clippd_tournaments(frm, to):
    out, seen, off = [], set(), 0
    while True:
        q = urllib.parse.urlencode({"gender": "Women", "division": "NCAA Division I", "startDate[from]": frm,
                                    "startDate[to]": to, "offset": off, "limit": 100,
                                    "sort[0][attribute]": "startDate", "sort[0][order]": "asc",
                                    "sort[1][attribute]": "tournamentId", "sort[1][order]": "asc"})
        res = fetch_json(f"{CLIPPD}/api/tournaments?{q}").get("results", [])
        new = [r for r in res if r["tournamentId"] not in seen]
        for r in new:
            seen.add(r["tournamentId"])
        out += new
        if len(res) < 100 or not new or off > 3000:
            return out
        off += 100


def clippd_board(tid):
    """Clasificación individual de un torneo de Clippd, sacada de los datos que trae la página."""
    u = fetch(f"{CLIPPD}/tournaments/{tid}/scoring/player").replace('\\"', '"')
    parts = u.split('"playerId":"')
    rows, seen = [], set()
    for i in range(1, len(parts)):
        ch = parts[i]
        m = re.match(r'(\d+)","playerName":"([^"]*)","playerType":"(\w+)"', ch)
        if not m or m.group(1) in seen:
            continue
        seen.add(m.group(1))

        def g(rx, default=None):
            mm = re.search(rx, ch)
            return mm.group(1) if mm else default

        def nums(s):
            return [None if x in ("null", "") else int(float(x)) for x in (s or "").split(",")] if s else []

        sch = re.findall(r'"schoolId":"(\d+)","schoolName":"([^"]*)"', parts[i - 1])
        rank = g(r'"currentRank":(\d+)')
        statuses = re.findall(r'"playerStatus":"(\w+)"', ch)
        rows.append({
            "cid": m.group(1), "name": m.group(2), "ind": m.group(3) != "team",
            "school": sch[-1][0] if sch else None,
            "toPar": nums(g(r'"scores":\[([^\]]*)\]')),
            "total": None if g(r'"totalScore":(-?\d+|null)') in (None, "null") else int(g(r'"totalScore":(-?\d+)')),
            "strokes": nums(g(r'"strokes":\[([^\]]*)\],"totalStrokes"')),
            "round": int(g(r'"currentRound":(\d+)', "0")),
            "thru": g(r'"holeThrough":"?([^",}]*)', ""),
            "rank": int(rank) if rank else None,
            "status": [s for s in statuses if s not in ("PLAYED", "PLAYING", "NOT_STARTED")],
        })
    ranked = [r for r in rows if r["rank"]]
    ties(ranked)
    for r in rows:
        r.setdefault("pos", "—")
    return rows, len(ranked)


def match_event(sched_uni, extra_uni, t):
    """Busca en el calendario de la universidad el torneo de Clippd (misma semana y nombre parecido)."""
    a = d(t["startDate"])
    words = {w for w in norm(t["tournamentName"]) if len(w) > 3} - {"invitational", "intercollegiate", "classic", "collegiate", "women", "womens", "championship", "presented"}
    best = None
    for e in sched_uni + extra_uni:
        if e["id"] == "c" + t["tournamentId"]:
            return e["id"]
        gap = abs((d(e["a"]) - a).days)
        if gap > 3:
            continue
        overlap = len(words & set(norm(e["n"])))
        score = overlap * 10 - gap
        if overlap or gap == 0:
            if not best or score > best[0]:
                best = (score, e["id"])
    return best[1] if best else None


def run_clippd(cfg, pls, sched, auto, estado):
    cids = cfg.get("clippd", {})
    ncaa = {p["id"]: p for p in pls if p["mode"] == "ncaa"}
    by_cid = {c: pid for pid, c in cids.items() if pid in ncaa}
    schools = estado.setdefault("escuelas", {})            # pid -> schoolId de Clippd
    frm = "2026-08-15" if "--temporada" in ARGS else (TODAY - timedelta(days=12)).isoformat()
    to = (TODAY + timedelta(days=120)).isoformat()
    tours = clippd_tournaments(frm, to)
    log(f"Clippd: {len(tours)} torneos NCAA femeninos entre {frm} y {to}")
    ev_auto = auto["ev"].setdefault("ncaa", {})
    res = auto["res"]["ncaa"]
    n_ev = n_res = 0
    for t in tours:
        tid = t["tournamentId"]
        cp, cs = set(t.get("competingPlayers") or []), set(t.get("competingSchools") or [])
        who = {pid for c, pid in by_cid.items() if c in cp} | {pid for pid, s in schools.items() if s in cs and pid in ncaa}
        if not who:
            continue
        a, b = t["startDate"][:10], (t.get("endDate") or t["startDate"])[:10]
        stroke = (t.get("eventType") or "Stroke Play").lower().startswith("stroke")
        url = f"{CLIPPD}/tournaments/{tid}/scoring/player"
        loc = " · ".join(x for x in [t.get("venue") or "", ", ".join(x for x in [t.get("city"), t.get("state")] if x)] if x)
        started = d(a) <= TODAY
        live = d(a) <= TODAY <= d(b) + timedelta(days=1) and not t.get("isComplete")
        fresh = d(b) >= TODAY - timedelta(days=4)
        rows, field = None, 0
        known = {p: match_event(sched.get(ncaa[p]["u"], []), ev_auto.get(ncaa[p]["u"], []), t) for p in who}
        missing = any(not known[p] or known[p] not in res.get(p, {}) for p in who)
        if started and stroke and (live or fresh or missing or "--temporada" in ARGS):
            try:
                rows, field = clippd_board(tid)
            except Exception as e:
                auto["errores"].append(f"Clippd {tid}: {e}")
        if started and not live:
            # Torneo ya jugado: solo cuenta para quien aparece en la clasificación (o ya estaba en su calendario).
            played = {by_cid[r["cid"]] for r in (rows or []) if r["cid"] in by_cid}
            who = {p for p in who if p in played or known[p]}
        eid_for = {}
        for pid in sorted(who):
            uni = ncaa[pid]["u"]
            ex = ev_auto.setdefault(uni, [])
            eid = known.get(pid) or match_event(sched.get(uni, []), ex, t)
            team_entry = schools.get(pid) in cs
            if not eid:
                eid = "c" + tid
                ex.append({"id": eid, "n": t["tournamentName"], "a": a, "b": b, "loc": loc or "Sede por confirmar",
                           "fmt": "stroke" if stroke else "match", "src": url,
                           **({} if team_entry else {"ind": True, "only": [pid]})})
                n_ev += 1
                log(f"  + torneo nuevo para {uni}: {t['tournamentName']} ({a})")
            elif not team_entry:
                for e in ex:  # entrada individual: que no salga a sus compañeras como «No alineada»
                    if e["id"] == eid and "only" in e and pid not in e["only"]:
                        e["only"].append(pid)
            eid_for[pid] = eid
        if not rows:
            continue
        for r in rows:  # aprende la universidad de cada jugadora para ver sus torneos futuros
            if r["cid"] in by_cid and r["school"]:
                schools[by_cid[r["cid"]]] = r["school"]
        for pid, eid in eid_for.items():
            r = next((x for x in rows if x["cid"] == cids.get(pid)), None)
            if not r:
                continue
            done = [s for s in r["strokes"] if s and s > 50]
            in_play = live and not (r["thru"] in ("18", "F", "") and r["round"] >= (t.get("plannedRounds") or t.get("numRounds") or 0))
            out = {"pos": r["pos"], "rounds": [str(s) for s in done], "tp": r["total"], "field": field,
                   "holes": 18 * len(done) or None, "src": url}
            if done and r["total"] is not None and not in_play:
                out["tot"] = sum(done)
            if r["ind"]:
                out["ind"] = True
            if "WD" in r["status"] or "DQ" in r["status"]:
                out["pos"] = "RET" if "WD" in r["status"] else "DQ"
            if in_play:
                out["live"] = True
                out["note"] = "Provisional" + (f" · vuelta {r['round']}, hoyo {r['thru']}" if r["thru"] not in ("", "0", "18", "F") else "")
            res.setdefault(pid, {})[eid] = out
            n_res += 1
    log(f"Clippd: {n_ev} torneos nuevos en calendarios, {n_res} resultados leídos")


# ------------------------------------------------------- Ladies European Tour

def run_let(cfg, pls, auto):
    for f in cfg.get("let", []):
        a, b = d(f["a"]), d(f["b"])
        if not (a - timedelta(days=1) <= TODAY <= b + timedelta(days=3)) and "--temporada" not in ARGS:
            continue
        url = f"https://api.euro.ocs-software.com/let/cache/let/{f['year']}/{f['year']}-{f['tid']}-scores-latest.json"
        try:
            E = fetch_json(url)["scores"]["scores_entry"]
        except Exception as e:
            auto["errores"].append(f"LET {f['event']}: {e}")
            continue
        rows = []
        for e in E:
            rounds = [e.get(f"score_R{i}", "") for i in range(1, 5)]
            done = [x for x in rounds if re.fullmatch(r"\d{2,3}", x or "")]
            pos = (e.get("pos") or "").strip()
            cur = next((i for i in range(4, 0, -1) if any(h for h in (e.get(f"hole_scores_R{i}") or "").split(",") if h.strip())), 0)
            thru = sum(1 for h in (e.get(f"hole_scores_R{cur}") or "").split(",") if h.strip()) if cur else 0
            rows.append({"name": e.get("name", ""), "pos": pos, "rank": int(pos) if pos.isdigit() else None,
                         "tp": tp_from(e.get("vspar", "")), "done": done, "cur": cur, "thru": thru,
                         "tee": e.get("time_R1", ""), "score": e.get("score")})
        ranked = [r for r in rows if r["rank"]]
        ties(ranked)
        field = len(E)
        live = TODAY <= b
        web = f.get("web", "https://ladieseuropeantour.com/")
        for p in pls:
            if p["mode"] not in f.get("modes", ["nac", "ncaa"]):
                continue
            r = next((x for x in rows if same_person(p["n"], x["name"])), None)
            if not r or (not r["done"] and not r["thru"]):
                continue  # aún no ha empezado: la web ya la muestra como «Próximo» o «En vivo»
            out = {"pos": r.get("pos") if r["rank"] else (r["pos"] or "—"), "rounds": r["done"], "tp": r["tp"],
                   "field": field, "holes": 18 * len(r["done"]) or None, "ind": True, "src": web}
            if r["pos"] in ("MC", "CUT"):
                out["pos"] = "Corte"; out["note"] = "No pasó el corte"
            elif r["pos"] in ("WD", "RTD", "DQ"):
                out["pos"] = "RET"
            if r["done"] and not live:
                out["tot"] = sum(int(x) for x in r["done"])
            if live:
                out["live"] = True
                out["note"] = "Provisional" + (f" · vuelta {r['cur']}, hoyo {r['thru']}" if 0 < r["thru"] < 18 else "")
            auto["res"][p["mode"]].setdefault(p["id"], {})[f["event"]] = out
            log(f"LET {f['event']}: {p['n']} {out['pos']} ({out['tp']})")


# ------------------------------------------------------------------- WAGR

def run_wagr(pls, auto):
    q = urllib.parse.urlencode({"rankingsType": 1, "pageNumber": 1, "week": 0, "year": 0, "region": 0, "countries": 3,
                                "playerName": "", "county": "", "pageSize": 2000, "playerIDs": "", "age": "", "asOfDate": "",
                                "includeFirstStats": "false", "sortString": "", "isRangeUnder": "false",
                                "isRangeOver": "false", "isThisAgeOnly": "false"})
    L = fetch_json(f"https://worldgolfranking2021api.wagr.com/api/wagr/rankings/getRankings?{q}")["rankingLandingModels"]
    L = [x for x in L if x.get("gender") == "F"]
    ym = TODAY.strftime("%Y-%m")
    snap = auto["wh"].setdefault(ym, {})
    n = 0
    for p in pls:
        if p["mode"] != "ncaa":
            continue
        hits = [x for x in L if same_person(p["n"], x["playerFullName"])]
        if len(hits) == 1:  # si el nombre coincide con varias, no se arriesga
            auto["wagr"][p["id"]] = hits[0]["rankThisWeek"]
            snap[p["id"]] = hits[0]["rankThisWeek"]
            n += 1
    log(f"WAGR: {len(L)} españolas en el ranking, {n} jugadoras NCAA actualizadas")


# --------------------------------------------------------- RFEG (livegolfscoring)

def cells(tr):
    return [re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", c))).strip()
            for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)]


def read_lgs(url):
    t = fetch(url)
    i = t.find('id="ordenacion"')
    if i < 0:
        raise ValueError("no encuentro la tabla de clasificación")
    tab = t[i:t.find("</table>", i)]
    head = cells(re.search(r"<thead.*?</thead>", tab, re.S).group(0))
    body = re.search(r"<tbody.*?</tbody>", tab, re.S).group(0)
    rows = [r for r in (cells(tr) for tr in re.findall(r"<tr[^>]*>.*?</tr>", body, re.S)) if len(r) == len(head)]
    col = {h: k for k, h in enumerate(head)}
    rcols = [k for k, h in enumerate(head) if re.fullmatch(r"\d", h)]
    out = []
    for r in rows:
        tot = r[col["Total"]] if "Total" in col and r[col["Total"]].isdigit() else None
        out.append({"name": r[col["Nombre"]], "pos": r[col["Pos."]], "tp": tp_from(r[col["Al Par"]]) if "Al Par" in col else None,
                    "rounds": [r[k] for k in rcols if re.fullmatch(r"\d{2,3}", r[k])],
                    "tot": int(tot) if tot else None, "hoyo": r[col["Hoyo"]] if "Hoyo" in col else ""})
    return out


def run_lgs(cfg, pls, auto):
    for f in cfg.get("lgs", []):
        a, b = d(f["a"]), d(f["b"])
        if not (a <= TODAY <= b + timedelta(days=3)) and "--temporada" not in ARGS:
            continue
        try:
            rows = read_lgs(f["url"])
        except Exception as e:
            auto["errores"].append(f'RFEG {f["event"]}: {e}')
            continue
        live = TODAY <= b
        for p in [p for p in pls if p["mode"] == f["mode"]]:
            hit = next((r for r in rows if same_person(p["n"], r["name"])), None)
            if not hit:
                continue
            r = {"pos": hit["pos"] or "—", "rounds": hit["rounds"], "tp": hit["tp"], "field": len(rows),
                 "holes": 18 * len(hit["rounds"]) or None, "src": f["url"]}
            if hit["tot"]:
                r["tot"] = hit["tot"]
            notes = [f["note"]] if f.get("note") else []
            if live:
                r["live"] = True
                notes.append("Provisional" + (f' · hoyo {hit["hoyo"]}' if hit["hoyo"] not in ("", "18", "F") else ""))
            if notes:
                r["note"] = " · ".join(notes)
            auto["res"][f["mode"]].setdefault(p["id"], {})[f["event"]] = r
            log(f"RFEG {f['event']}: {p['n']} {r['pos']}")


# -------------------------------------------------------------------- main

def main():
    cfg = json.loads((PIPE / "fuentes.json").read_text(encoding="utf-8"))
    est_p = PIPE / "estado.json"
    estado = json.loads(est_p.read_text(encoding="utf-8")) if est_p.exists() else {}
    auto_p = SITE / "auto.js"
    old = auto_p.read_text(encoding="utf-8")
    auto = json.loads(old[old.index("{"):old.rindex("}") + 1])
    for k, v in {"res": {"ncaa": {}, "nac": {}}, "ev": {"ncaa": {}, "nac": []}, "wagr": {}, "wh": {}}.items():
        auto.setdefault(k, v)
    auto["res"].setdefault("ncaa", {}); auto["res"].setdefault("nac", {})
    old_upd = auto.get("upd")
    before = json.dumps({k: auto[k] for k in ("res", "ev", "wagr", "wh")}, sort_keys=True)
    auto["errores"] = []
    pls, sched = site_data()
    log(f"Web: {sum(p['mode']=='ncaa' for p in pls)} jugadoras NCAA, {sum(p['mode']=='nac' for p in pls)} nacionales, {len(sched)} calendarios de universidad")

    for name, fn in [("Clippd", lambda: run_clippd(cfg, pls, sched, auto, estado)),
                     ("LET", lambda: run_let(cfg, pls, auto)),
                     ("WAGR", lambda: run_wagr(pls, auto)),
                     ("RFEG", lambda: run_lgs(cfg, pls, auto))]:
        try:
            fn()
        except Exception as e:  # una fuente caída no tumba a las demás
            auto["errores"].append(f"{name}: {e}")
            log(f"::warning::{name} falló: {e}")

    auto["upd"] = f"{TODAY.day} {MES[TODAY.month - 1]}"
    auto["rev"] = NOW.isoformat(timespec="seconds")
    changed = json.dumps({k: auto[k] for k in ("res", "ev", "wagr", "wh")}, sort_keys=True) != before
    if "--prueba" in ARGS:
        Path("/tmp/auto_prueba.json").write_text(json.dumps(auto, ensure_ascii=False))
        log("Prueba: no se escribe nada (resultado en /tmp/auto_prueba.json).")
        log(json.dumps(auto, ensure_ascii=False)[:4000])
        return 0
    auto_p.write_text("/* Lo genera pipeline/actualizar.py. No editar a mano. */\nwindow.AUTO=" +
                      json.dumps(auto, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    est_p.write_text(json.dumps(estado, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as g:
            g.write(f"cambios={'1' if changed else '0'}\nnuevo_dia={'1' if auto['upd'] != old_upd else '0'}\n")
    log(f"Cambios: {'sí' if changed else 'no'}. Errores: {auto['errores'] or 'ninguno'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
