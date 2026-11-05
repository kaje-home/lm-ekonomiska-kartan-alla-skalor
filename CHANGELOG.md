# Ändringar

## 0.1.0 (2026-11-05)

- Första utgåvan. Ekonomiska kartan över ett område i 1:10 000 eller 1:20 000 efter vad som finns, georefererad, klippt per blad med alfaband, med VRT, bladlager och rapport.
- 1:20 000-bladen georefereras mot kartans eget rutnät eller mot kilometerstrecken i marginalen. Metoden och dess spärrar är desamma som i LM Fältunderlag 0.9.80 (metodversion "2026-09-27 kant 6 m").
- Sökningen täcker hela 1:10 000-serien, även block 1–9 (södra Sverige) och blad med tillägg i namnet, och väljer nyaste, äldsta eller alla utgåvor.
- Världsfilen för 1:10 000-bladen granskas: ett blad vars skanning tryckts ihop till sin ruta lämnas utanför.
- En ruta som bara nuddar området i en kant eller ett hörn tas inte med.
- Automatiskt läge: där båda skalorna finns gäller utgåvevalet även mellan dem (nyaste: det yngsta bladet, äldsta: det äldsta, samma år: 1:10 000). VRT:n ordnas efter samma regel, också med *Båda serierna*, och rapporten säger vilket blad som ligger överst där skalorna överlappar.
- Provat i QGIS 3.44 och 4.2.
