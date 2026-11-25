#!/usr/bin/env python3
"""Actualización automática de la web de golfistas españolas.

Lee las clasificaciones de los torneos de pipeline/feeds.json que están en juego
(o terminaron hace 3 días o menos), empareja a las jugadoras por nombre y
escribe site/auto.js. La web mezcla auto.js con sus datos al cargar.
No toca index.html. Si una fuente falla, conserva lo que había y sigue.
"""
import html, json, re, sys, unicodedata, urllib.request
from datetime import datetime, date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
SITE, PIPE = ROOT / "site", ROOT / "pipeline"
TZ = ZoneInfo("Europe/Madrid")
MES = ["ene","feb","mar","abr","may","jun","jul","ago","sep","oct","nov","dic"]
UA = {"User-Agent": "Mozilla/5.0 (compatible; espanolas-golf/1.0; +https://github.com)"}

def norm(s):
    s = unicodedata.normalize("NFD", html.unescape(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z ]+", " ", s).split()

def players():
    """Saca id, nombre y modo de cada jugadora de index.html (los dos formatos que usa)."""
    t = (SITE / "index.html").read_text(encoding="utf-8")
    nac0 = t.index("const NAC_P=")
    out = []
    for m in re.finditer(r'\{\s*"?id"?\s*:\s*"([a-z0-9]+)"\s*,\s*"?n"?\s*:\s*"([^"]+)"', t):
        out.append({"id": m.group(1), "n": m.group(2), "mode": "nac" if m.start() > nac0 else "ncaa"})
    return out

def matches(pname, row_name):
    """«APELLIDO APELLIDO, Nombre» frente a «Nombre Apellido Apellido»: nombre y primer apellido deben coincidir."""
    if "," in row_name:
        sur, first = row_name.split(",", 1)
    else:
        parts = row_name.split(); first, sur = parts[0], " ".join(parts[1:])
    pt, st, ft = norm(pname), norm(sur), norm(first)
    if not st or not ft: return False
    return ft[0] in pt and st[0] in pt and pt.index(ft[0]) < pt.index(st[0])

def fetch(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r:
        return r.read().decode("utf-8", "replace")

def cells(tr):
    return [re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", c))).strip()
            for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)]

def read_lgs(url):
    """Clasificación de livegolfscoring / mitarjeta: tabla #ordenacion."""
    t = fetch(url)
    i = t.find('id="ordenacion"')
    if i < 0: raise ValueError("no encuentro la tabla de clasificación")
    tab = t[i:t.find("</table>", i)]
    head = cells(re.search(r"<thead.*?</thead>", tab, re.S).group(0))
    body = re.search(r"<tbody.*?</tbody>", tab, re.S).group(0)
    rows = [cells(tr) for tr in re.findall(r"<tr[^>]*>.*?</tr>", body, re.S)]
    rows = [r for r in rows if len(r) == len(head)]
    col = {h: k for k, h in enumerate(head)}
    rcols = [k for k, h in enumerate(head) if re.fullmatch(r"\d", h)]
    out = []
    for r in rows:
        tp = r[col.get("Al Par", -1)] if "Al Par" in col else ""
        tpn = 0 if tp in ("E", "PAR", "0") else (int(tp.replace("+", "")) if re.fullmatch(r"[+-]?\d+", tp) else None)
        rounds = [r[k] for k in rcols if re.fullmatch(r"\d{2,3}", r[k])]
        tot = r[col["Total"]] if "Total" in col and r[col["Total"]].isdigit() else None
        out.append({"name": r[col["Nombre"]], "pos": r[col["Pos."]], "tp": tpn, "rounds": rounds,
                    "tot": int(tot) if tot else None, "hoyo": r[col["Hoyo"]] if "Hoyo" in col else ""})
    return out, len(rcols)

READERS = {"lgs": read_lgs}

def main():
    now = datetime.now(TZ); today = now.date()
    feeds = json.loads((PIPE / "feeds.json").read_text(encoding="utf-8"))["feeds"]
    auto_p = SITE / "auto.js"
    old = auto_p.read_text(encoding="utf-8")
    auto = json.loads(old[old.index("{"):old.rindex("}") + 1])
    res = auto.setdefault("res", {}); res.setdefault("ncaa", {}); res.setdefault("nac", {})
    before = json.dumps(res, sort_keys=True)
    old_upd = auto.get("upd")
    pls = players(); errors = []; touched = 0
    force = "--todos" in sys.argv
    for f in feeds:
        a, b = date.fromisoformat(f["a"]), date.fromisoformat(f["b"])
        if not force and not (a <= today <= b + timedelta(days=3)):
            continue
        try:
            rows, nrounds = READERS[f["type"]](f["url"])
        except Exception as e:
            errors.append(f'{f["event"]}: {e}'); continue
        live = today <= b
        field = len(rows)
        for p in [p for p in pls if p["mode"] == f["mode"]]:
            want = f.get("players", {}).get(p["id"])
            hit = next((r for r in rows if (want and norm(want) == norm(r["name"])) or (not want and matches(p["n"], r["name"]))), None)
            if not hit: continue
            r = {"pos": hit["pos"] or "—", "rounds": hit["rounds"], "tp": hit["tp"], "field": field,
                 "holes": 18 * len(hit["rounds"]) if hit["rounds"] else None, "src": f["url"]}
            if hit["tot"]: r["tot"] = hit["tot"]
            notes = [f.get("note")] if f.get("note") else []
            if live: r["live"] = True; notes.append("Provisional" + (f' · hoyo {hit["hoyo"]}' if hit["hoyo"] not in ("", "18", "F") else ""))
            if notes: r["note"] = " · ".join(notes)
            res[f["mode"]].setdefault(p["id"], {})[f["event"]] = r; touched += 1
    auto["upd"] = f"{today.day} {MES[today.month-1]}"
    auto["rev"] = now.isoformat(timespec="seconds")
    auto["errores"] = errors
    auto_p.write_text("/* Lo genera pipeline/actualizar.py cada día. No editar a mano. */\nwindow.AUTO=" +
                      json.dumps(auto, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    changed = json.dumps(res, sort_keys=True) != before
    import os
    if os.environ.get("GITHUB_OUTPUT"):
        # nuevo_dia: primera pasada del día (aunque GitHub la retrase horas) → se guarda para que la fecha «Actualizado» sea la de hoy.
        with open(os.environ["GITHUB_OUTPUT"], "a") as g:
            g.write(f"cambios={'1' if changed else '0'}\nnuevo_dia={'1' if auto['upd'] != old_upd else '0'}\n")
    print(f"Resultados leídos: {touched}. Cambios: {'sí' if changed else 'no'}. Errores: {errors or 'ninguno'}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
