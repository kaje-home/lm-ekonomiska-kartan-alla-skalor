# LM Ekonomiska kartan – alla skalor

Fristående tillägg till QGIS, inte från Lantmäteriet. Hämtar Lantmäteriets ekonomiska karta (öppna data, CC0) över ett område och levererar georefererade blad i 1:10 000 eller 1:20 000; 1:20 000-bladen georefereras mot kartans eget tryckta rutnät. Där båda skalorna finns avgör utgåvevalet (nyaste eller äldsta) vilket blad som tas.

Öppna **Insticksprogram → Ekonomiska kartan → Hämta ekonomiska kartan…**, välj område och utmapp och tryck *Hämta*. I utmappen hamnar bladen (`blad/`, tryckåret i filnamnet), en VRT över hela området, bladlagret `blad.gpkg` och `rapport.txt` med källa, år, metod och lägesfel per blad.

Som område går också *Rutor ur ett rutnät*. *Bygg bladrutnät* ger alla blad i båda skalorna med år och utgåvor; markera de du vill ha. *Skapa fast rutnät…* ger rutor i SWEREF 99 TM med jämna koordinater. Med *En GeoTIFF per ruta* skärs varje ruta ut som en egen bricka i `brickor/`, med samma pixelstorlek och pixelrutnät i alla brickor.

Samma sak finns som Processing-algoritmer, `lmeko:hamta_ekonomiska_kartan`, `lmeko:bladrutnat` och `lmeko:fast_rutnat`, för batch och Model Designer.

Bladen är från olika år (1942–1988), och VRT:n blandar dem. Ett blad som inte klarar kontrollerna lämnas utanför, med orsaken i rapporten. Hela beskrivningen, med kända begränsningar: README på https://github.com/kaje-home/lm-ekonomiska-kartan-alla-skalor
