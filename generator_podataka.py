#!/usr/bin/env python3
"""
generator_podataka.py
Generator sintetickih ispisa poziva i poruka sa skrivenim scenarijem.

Izlaz (u mapi --izlaz, zadano: podaci/):
  pozivi.csv            pozivatelj, primatelj, datum_vrijeme, trajanje_s, tip, bazna_stanica
  bazne_stanice.csv     oznaka, sirina, duzina
  scenarij_istina.json  "rjesenje" scenarija - sluzi SAMO za evaluaciju,
                        aplikacija ga ne smije citati

Napomena: bazna_stanica je stanica na koju je u trenutku komunikacije bio
spojen POZIVATELJ (lokacija primatelja nije poznata).

Pokretanje:
  python generator_podataka.py
  python generator_podataka.py --sjeme 7 --izlaz podaci2
  python generator_podataka.py --bez-gresaka     # cisti podaci, bez "prljanja"
"""

import argparse
import csv
import json
import math
import random
from datetime import datetime, timedelta
from itertools import combinations
from pathlib import Path

# --------------------------------------------------------------------------
# Postavke
# --------------------------------------------------------------------------
SJEME = 42

POCETAK = datetime(2026, 3, 1)             # prvi dan ispisa
BROJ_DANA = 60                             # duljina promatranog razdoblja
DOGADJAJ = datetime(2026, 4, 21, 23, 30)   # provala
DANA_ESKALACIJE = 7                        # koliko dana prije dogadjaja pozivi ucestaju
DANA_TISINE = 3                            # tisina u grupi nakon dogadjaja
DANA_POTROSNOG = 5                         # koliko dana zivi potrosni ("burner") broj

SUSRET_OD = DOGADJAJ.replace(hour=20, minute=30)   # grupa se okuplja
SUSRET_DO = DOGADJAJ + timedelta(hours=1)          # i razilazi

BROJ_OBICNIH = 100     # sum
BROJ_CLANOVA = 3       # obicni clanovi grupe A (uz vodju i posrednika = 5 osoba)
BROJ_GRUPE_B = 4       # druga grupa, s kojom komunicira samo posrednik
BROJ_STANICA = 40

# Podrucje Zagreba
LAT_MIN, LAT_MAX = 45.76, 45.84
LON_MIN, LON_MAX = 15.88, 16.06

# Namjerne greske u podacima (da modul za ciscenje ima posla)
UDIO_DUPLIKATA = 0.01
UDIO_BEZ_STANICE = 0.003
UDIO_DRUGOG_FORMATA_BROJA = 0.20
UDIO_DRUGOG_FORMATA_DATUMA = 0.15
UDIO_DRUGOG_PISANJA_TIPA = 0.05

MREZNE_GRUPE = ["91", "92", "95", "97", "98", "99"]

# Tezine po satima (0-23): kada tko komunicira
SATI_OBICNI = [0.2, 0.1, 0.05, 0.05, 0.05, 0.1, 0.5, 2, 4, 5, 5, 5,
               5, 5, 5, 5, 6, 7, 8, 8, 7, 5, 2, 0.6]
SATI_GRUPA = [1, 0.5, 0.2, 0.1, 0.1, 0.1, 0.3, 1, 2, 2, 2, 2,
              2, 2, 2, 3, 3, 4, 5, 6, 6, 5, 4, 2]
SATI_ESKALACIJA = [7, 6, 5, 3, 1, 0.3, 0.3, 0.5, 1, 1, 1, 1,
                   1, 1, 1, 1, 2, 2, 3, 4, 5, 6, 8, 8]


# --------------------------------------------------------------------------
# Pomocne funkcije
# --------------------------------------------------------------------------
def poisson(rng, lam):
    """Slucajan broj dogadjaja u danu uz prosjek lam (Knuthov algoritam)."""
    if lam <= 0:
        return 0
    granica = math.exp(-lam)
    k, p = 0, 1.0
    while True:
        p *= rng.random()
        if p <= granica:
            return k
        k += 1


def slucajno_vrijeme(rng, dan, tezine_sati):
    """Slucajan trenutak unutar zadanog dana, sat biran prema tezinama."""
    sat = rng.choices(range(24), weights=tezine_sati)[0]
    return dan.replace(hour=sat, minute=rng.randrange(60), second=rng.randrange(60))


def novi_broj(rng, zauzeti):
    """Jedinstven mobilni broj u kanonskom obliku +3859XXXXXXXXX."""
    while True:
        broj = "+385" + rng.choice(MREZNE_GRUPE) + f"{rng.randrange(10**7):07d}"
        if broj not in zauzeti:
            zauzeti.add(broj)
            return broj


# --------------------------------------------------------------------------
# Svijet: stanice i osobe
# --------------------------------------------------------------------------
def stvori_stanice(rng):
    """Bazne stanice rasporedjene u mrezu preko grada, s malim pomakom."""
    stupaca = 8
    redaka = math.ceil(BROJ_STANICA / stupaca)
    stanice = []
    for i in range(BROJ_STANICA):
        r, s = divmod(i, stupaca)
        sirina = LAT_MIN + (r + 0.5) * (LAT_MAX - LAT_MIN) / redaka + rng.uniform(-0.004, 0.004)
        duzina = LON_MIN + (s + 0.5) * (LON_MAX - LON_MIN) / stupaca + rng.uniform(-0.006, 0.006)
        stanice.append({"oznaka": f"BS{i + 1:03d}",
                        "sirina": round(sirina, 6),
                        "duzina": round(duzina, 6)})
    return stanice


def stvori_osobu(rng, zauzeti, oznake, uloga, aktivnost):
    """Osoba ima broj, stanicu doma i posla, kontakte i prosjecan broj
    odlaznih komunikacija dnevno (aktivnost)."""
    return {"broj": novi_broj(rng, zauzeti),
            "uloga": uloga,
            "dom": rng.choice(oznake),
            "posao": rng.choice(oznake),
            "kontakti": {},          # broj -> tezina (koliko cesto ga zove)
            "aktivnost": aktivnost}


def povezi(a, b, tezina):
    a["kontakti"][b["broj"]] = tezina
    b["kontakti"][a["broj"]] = tezina


def stvori_obicne(rng, zauzeti, oznake):
    """Stotinjak obicnih korisnika organiziranih u krugove (obitelj, prijatelji,
    kolege) uz pokoji kontakt izvan kruga - da sum ima realnu strukturu."""
    obicni = [stvori_osobu(rng, zauzeti, oznake, "obican", rng.uniform(1.5, 6))
              for _ in range(BROJ_OBICNIH)]
    i = 0
    while i < len(obicni):
        velicina = rng.randint(4, 8)
        for a, b in combinations(obicni[i:i + velicina], 2):
            povezi(a, b, rng.uniform(1, 5))
        i += velicina
    for osoba in obicni:
        for _ in range(rng.randint(1, 3)):
            drugi = rng.choice(obicni)
            if drugi is not osoba and drugi["broj"] not in osoba["kontakti"]:
                povezi(osoba, drugi, rng.uniform(0.3, 1.5))
    return obicni


def lokacija(rng, osoba, t, oznake, prisilno):
    """Stanica na kojoj je osoba u trenutku t. Radnim danom je na poslu,
    nocu doma, inace negdje po gradu. 'prisilno' nadjacava sve (susret)."""
    for od, do, stanica in prisilno.get(osoba["broj"], []):
        if od <= t <= do:
            return stanica
    if t.weekday() < 5 and 8 <= t.hour < 17:
        return osoba["posao"] if rng.random() < 0.85 else rng.choice(oznake)
    if t.hour >= 22 or t.hour < 7:
        return osoba["dom"] if rng.random() < 0.95 else rng.choice(oznake)
    return rng.choices([osoba["dom"], osoba["posao"], rng.choice(oznake)],
                       weights=[5, 1, 4])[0]


# --------------------------------------------------------------------------
# Komunikacija
# --------------------------------------------------------------------------
def zapis(rng, pozivatelj, primatelj, t, stanica, udio_sms, prosjek_trajanja):
    if rng.random() < udio_sms:
        tip, trajanje = "SMS", 0
    else:
        tip, trajanje = "poziv", max(3, int(rng.expovariate(1 / prosjek_trajanja)))
    return {"pozivatelj": pozivatelj, "primatelj": primatelj, "datum_vrijeme": t,
            "trajanje_s": trajanje, "tip": tip, "bazna_stanica": stanica}


def svakodnevna_komunikacija(rng, osobe, oznake, prisilno):
    """Obican zivot: svatko zove svoje kontakte. Vrijedi i za clanove grupa,
    koji uz scenarij imaju i normalne kontakte."""
    redci = []
    for osoba in osobe:
        kontakti = list(osoba["kontakti"])
        tezine = list(osoba["kontakti"].values())
        if not kontakti:
            continue
        for d in range(BROJ_DANA):
            dan = POCETAK + timedelta(days=d)
            for _ in range(poisson(rng, osoba["aktivnost"])):
                t = slucajno_vrijeme(rng, dan, SATI_OBICNI)
                primatelj = rng.choices(kontakti, weights=tezine)[0]
                redci.append(zapis(rng, osoba["broj"], primatelj, t,
                                   lokacija(rng, osoba, t, oznake, prisilno),
                                   udio_sms=0.4, prosjek_trajanja=120))
    return redci


def faza(dan):
    """Vraca (mnozitelj ucestalosti grupe A, tezine sati) za zadani dan."""
    do_dogadjaja = (DOGADJAJ.date() - dan.date()).days
    if do_dogadjaja < 0:                               # nakon dogadjaja
        if -do_dogadjaja <= DANA_TISINE:
            return 0.0, SATI_GRUPA
        return 0.3, SATI_GRUPA
    if do_dogadjaja < DANA_ESKALACIJE:                 # eskalacija: 2x -> 5x
        napredak = (DANA_ESKALACIJE - 1 - do_dogadjaja) / (DANA_ESKALACIJE - 1)
        return 2 + 3 * napredak, SATI_ESKALACIJA
    return 1.0, SATI_GRUPA                             # mirno razdoblje


def komunikacija_scenarija(rng, bridovi, osobe_po_broju, oznake, prisilno):
    """Komunikacija unutar grupa. Svaki brid je (a, b, dnevna stopa,
    vjerojatnost da zove a, vrsta); vrsta 'A' prati faze scenarija,
    'AB' (posrednik - druga grupa) eskalira blaze, 'B' je stalna."""
    redci = []
    for d in range(BROJ_DANA):
        dan = POCETAK + timedelta(days=d)
        mnozitelj_a, sati_a = faza(dan)
        for a, b, stopa, p_a, vrsta in bridovi:
            if vrsta == "A":
                mnozitelj, sati = mnozitelj_a, sati_a
            elif vrsta == "AB":
                mnozitelj, sati = min(mnozitelj_a, 2.0), sati_a
            else:
                mnozitelj, sati = 1.0, SATI_GRUPA
            for _ in range(poisson(rng, stopa * mnozitelj)):
                t = slucajno_vrijeme(rng, dan, sati)
                if vrsta != "B" and t >= SUSRET_OD and t.date() == DOGADJAJ.date():
                    continue      # na susretu su zajedno, ne zovu se
                poz, prim = (a, b) if rng.random() < p_a else (b, a)
                redci.append(zapis(rng, poz, prim, t,
                                   lokacija(rng, osobe_po_broju[poz], t, oznake, prisilno),
                                   udio_sms=0.5, prosjek_trajanja=40))
    return redci


def komunikacija_potrosnog(rng, potrosni, vodja, posrednik, oznake, prisilno, osobe_po_broju):
    """Potrosni broj: pojavi se nekoliko dana prije dogadjaja, komunicira
    samo s vodjom i posrednikom i nestane."""
    redci = []
    prvi_dan = DOGADJAJ.replace(hour=0, minute=0) - timedelta(days=DANA_POTROSNOG - 1)
    for d in range(DANA_POTROSNOG):
        dan = prvi_dan + timedelta(days=d)
        for drugi in (vodja, posrednik):
            for _ in range(1 + poisson(rng, 1.0)):
                t = slucajno_vrijeme(rng, dan, SATI_ESKALACIJA)
                if t >= DOGADJAJ:
                    continue
                poz, prim = (potrosni, drugi) if rng.random() < 0.5 else (drugi, potrosni)
                redci.append(zapis(rng, poz["broj"], prim["broj"], t,
                                   lokacija(rng, osobe_po_broju[poz["broj"]], t, oznake, prisilno),
                                   udio_sms=0.7, prosjek_trajanja=25))
    return redci


def komunikacija_na_susretu(rng, grupa_a, vodja, posrednik, potrosni, kontakt_b, prisilno, oznake):
    """Svaki clan se tijekom susreta javi barem dvaput s iste stanice -
    tako susret postaje vidljiv u podacima."""
    redci = []
    trajanje_prozora = int((DOGADJAJ - timedelta(minutes=30) - SUSRET_OD).total_seconds())
    for osoba in grupa_a:
        if osoba is vodja:
            primatelji = [potrosni["broj"]]
        elif osoba is posrednik:
            primatelji = [potrosni["broj"], kontakt_b["broj"]]
        else:
            primatelji = [b for b in osoba["kontakti"]]   # obicni kontakti
        for _ in range(rng.randint(2, 3)):
            t = SUSRET_OD + timedelta(seconds=rng.randrange(trajanje_prozora))
            redci.append(zapis(rng, osoba["broj"], rng.choice(primatelji), t,
                               lokacija(rng, osoba, t, oznake, prisilno),
                               udio_sms=0.8, prosjek_trajanja=20))
    return redci


# --------------------------------------------------------------------------
# Namjerne greske ("prljanje")
# --------------------------------------------------------------------------
def oblik_broja(rng, broj, prljavo):
    if not prljavo or rng.random() >= UDIO_DRUGOG_FORMATA_BROJA:
        return broj
    nacionalni = broj[4:]                                   # npr. 911234567
    return rng.choice([
        "0" + nacionalni,                                                   # 0911234567
        "00385" + nacionalni,                                               # 00385911234567
        f"0{nacionalni[:2]} {nacionalni[2:5]} {nacionalni[5:]}",            # 091 123 4567
        f"+385 {nacionalni[:2]} {nacionalni[2:5]} {nacionalni[5:]}",        # +385 91 123 4567
        f"0{nacionalni[:2]}/{nacionalni[2:5]}-{nacionalni[5:]}",            # 091/123-4567
    ])


def oblik_retka(rng, r, prljavo):
    """Pretvara zapis u tekstualni redak CSV-a, uz povremene varijacije formata."""
    drugi_datum = prljavo and rng.random() < UDIO_DRUGOG_FORMATA_DATUMA
    tip = r["tip"]
    if prljavo and rng.random() < UDIO_DRUGOG_PISANJA_TIPA:
        tip = rng.choice([tip.lower(), tip.upper(), tip.capitalize(), f" {tip} "])
    stanica = r["bazna_stanica"]
    if prljavo and rng.random() < UDIO_BEZ_STANICE:
        stanica = ""
    return {
        "pozivatelj": oblik_broja(rng, r["pozivatelj"], prljavo),
        "primatelj": oblik_broja(rng, r["primatelj"], prljavo),
        "datum_vrijeme": r["datum_vrijeme"].strftime(
            "%d.%m.%Y. %H:%M:%S" if drugi_datum else "%Y-%m-%d %H:%M:%S"),
        "trajanje_s": r["trajanje_s"],
        "tip": tip,
        "bazna_stanica": stanica,
    }


def pripremi_retke(rng, redci, prljavo):
    """Duplikat se formatira iznova, pa je ponekad identican, a ponekad isti
    zapis u drugom formatu (otkriva se tek nakon ujednacavanja)."""
    izlaz = []
    for r in redci:
        izlaz.append(oblik_retka(rng, r, prljavo))
        if prljavo and rng.random() < UDIO_DUPLIKATA:
            izlaz.append(oblik_retka(rng, r, prljavo))
    return izlaz


# --------------------------------------------------------------------------
# Glavni program
# --------------------------------------------------------------------------
def generiraj(sjeme, prljavo):
    rng = random.Random(sjeme)
    stanice = stvori_stanice(rng)
    oznake = [s["oznaka"] for s in stanice]
    zauzeti = set()

    obicni = stvori_obicne(rng, zauzeti, oznake)

    # Grupa A (5 osoba) i grupa B
    vodja = stvori_osobu(rng, zauzeti, oznake, "vodja", rng.uniform(1, 2.5))
    posrednik = stvori_osobu(rng, zauzeti, oznake, "posrednik", rng.uniform(1, 2.5))
    clanovi = [stvori_osobu(rng, zauzeti, oznake, "clan", rng.uniform(1, 2.5))
               for _ in range(BROJ_CLANOVA)]
    grupa_a = [vodja, posrednik] + clanovi
    grupa_b = [stvori_osobu(rng, zauzeti, oznake, "grupa_b", rng.uniform(1, 2.5))
               for _ in range(BROJ_GRUPE_B)]
    kontakt_b = grupa_b[0]

    # I kriminalci imaju obitelj i prijatelje
    for osoba in grupa_a + grupa_b:
        for drugi in rng.sample(obicni, rng.randint(2, 4)):
            povezi(osoba, drugi, rng.uniform(0.5, 2))

    # Potrosni broj: jedna fiksna lokacija, bez obicnih kontakata
    potrosni = stvori_osobu(rng, zauzeti, oznake, "potrosni", 0)

    # Mjesto susreta: stanica koja nikome iz grupe nije ni dom ni posao
    poznate = {o[k] for o in grupa_a for k in ("dom", "posao")}
    stanica_susreta = rng.choice([s for s in oznake if s not in poznate])
    prisilno = {o["broj"]: [(SUSRET_OD, SUSRET_DO, stanica_susreta)] for o in grupa_a}
    prisilno[potrosni["broj"]] = [(POCETAK, POCETAK + timedelta(days=BROJ_DANA), potrosni["dom"])]

    # Bridovi scenarija: (a, b, dnevna stopa, vjerojatnost da zove a, vrsta)
    bridovi = [(vodja["broj"], posrednik["broj"], 0.40, 0.65, "A")]
    bridovi += [(vodja["broj"], c["broj"], 0.35, 0.65, "A") for c in clanovi]
    bridovi += [(a["broj"], b["broj"], 0.06, 0.5, "A")
                for a, b in combinations([posrednik] + clanovi, 2)]
    bridovi += [(posrednik["broj"], kontakt_b["broj"], 0.25, 0.5, "AB")]
    bridovi += [(a["broj"], b["broj"], 0.25, 0.5, "B") for a, b in combinations(grupa_b, 2)]

    sve_osobe = obicni + grupa_a + grupa_b
    po_broju = {o["broj"]: o for o in sve_osobe + [potrosni]}

    redci = svakodnevna_komunikacija(rng, sve_osobe, oznake, prisilno)
    redci += komunikacija_scenarija(rng, bridovi, po_broju, oznake, prisilno)
    redci += komunikacija_potrosnog(rng, potrosni, vodja, posrednik, oznake, prisilno, po_broju)
    redci += komunikacija_na_susretu(rng, grupa_a, vodja, posrednik, potrosni,
                                     kontakt_b, prisilno, oznake)
    redci.sort(key=lambda r: r["datum_vrijeme"])

    istina = {
        "sjeme": sjeme,
        "razdoblje": {"od": POCETAK.isoformat(sep=" "),
                      "do": (POCETAK + timedelta(days=BROJ_DANA)).isoformat(sep=" ")},
        "grupa_a": {"vodja": vodja["broj"],
                    "posrednik": posrednik["broj"],
                    "clanovi": [c["broj"] for c in clanovi]},
        "grupa_b": [o["broj"] for o in grupa_b],
        "kontakt_posrednika_u_grupi_b": kontakt_b["broj"],
        "potrosni_broj": potrosni["broj"],
        "dogadjaj": DOGADJAJ.isoformat(sep=" "),
        "pocetak_eskalacije": (DOGADJAJ.replace(hour=0, minute=0)
                               - timedelta(days=DANA_ESKALACIJE - 1)).isoformat(sep=" "),
        "tisina_nakon_dogadjaja_dana": DANA_TISINE,
        "susret": {"stanica": stanica_susreta,
                   "od": SUSRET_OD.isoformat(sep=" "),
                   "do": SUSRET_DO.isoformat(sep=" ")},
    }
    return stanice, pripremi_retke(rng, redci, prljavo), istina


def main():
    parser = argparse.ArgumentParser(description="Generator ispisa poziva sa skrivenim scenarijem.")
    parser.add_argument("--sjeme", type=int, default=SJEME, help="sjeme generatora slucajnih brojeva")
    parser.add_argument("--izlaz", default="podaci", help="izlazna mapa")
    parser.add_argument("--bez-gresaka", action="store_true",
                        help="ne ubacuj duplikate, razlicite formate i prazna polja")
    args = parser.parse_args()

    stanice, redci, istina = generiraj(args.sjeme, prljavo=not args.bez_gresaka)

    mapa = Path(args.izlaz)
    mapa.mkdir(parents=True, exist_ok=True)
    with open(mapa / "bazne_stanice.csv", "w", newline="", encoding="utf-8") as f:
        pisac = csv.DictWriter(f, fieldnames=["oznaka", "sirina", "duzina"])
        pisac.writeheader()
        pisac.writerows(stanice)
    with open(mapa / "pozivi.csv", "w", newline="", encoding="utf-8") as f:
        pisac = csv.DictWriter(f, fieldnames=["pozivatelj", "primatelj", "datum_vrijeme",
                                              "trajanje_s", "tip", "bazna_stanica"])
        pisac.writeheader()
        pisac.writerows(redci)
    with open(mapa / "scenarij_istina.json", "w", encoding="utf-8") as f:
        json.dump(istina, f, ensure_ascii=False, indent=2)

    print(f"Zapisano u '{mapa}/':")
    print(f"  pozivi.csv            {len(redci)} redaka")
    print(f"  bazne_stanice.csv     {len(stanice)} stanica")
    print(f"  scenarij_istina.json  (samo za evaluaciju)")


if __name__ == "__main__":
    main()
