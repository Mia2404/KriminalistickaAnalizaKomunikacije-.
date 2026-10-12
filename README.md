# Analiza komunikacije osumnjičenika

Aplikacija iz ispisa poziva i poruka više osoba otkriva tko je s kim povezan,
tko je u mreži najvažniji, gdje se tko kretao i kada se ponašanje promijenilo.
Svi podaci su sintetički i nastaju vlastitim generatorom u koji je ugrađen
skriveni scenarij, pa se na kraju može provjeriti je li ga aplikacija pronašla.

## Tehnologije

Python, Flask, SQLite, pandas, networkx, folium, pyvis

## Pokretanje

```
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python generator_podataka.py     # stvara podaci/pozivi.csv i podaci/bazne_stanice.csv
```

Generator uz podatke zapisuje i `podaci/scenarij_istina.json`. Ta datoteka sadrži
rješenje scenarija i služi samo za evaluaciju; aplikacija je ne čita.

## Plan rada

1. Generator podataka sa scenarijem
2. Učitavanje, čišćenje i baza
3. Graf kontakata i mjere središnjosti
4. Vremenska analiza i pravila
5. Karta i susreti
6. Flask sučelje i izvještaj
7. Evaluacija i dokumentacija

Minimalna verzija obuhvaća korake 1 do 4.
