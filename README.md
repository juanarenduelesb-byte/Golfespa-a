# Españolas · Golf femenino

Las golfistas españolas en la NCAA (EE. UU.) y en el circuito nacional: calendario, resultados, marcador en vivo y ranking.

## Cómo está montado

- `site/`: la web. Es estática (un solo `index.html` con los datos dentro) y la publica Cloudflare Pages cada vez que cambia algo en la rama `main`.
- `site/auto.js`: los resultados que se leen solos. Lo escribe la actualización; no se edita a mano. La web lo mezcla con sus datos al cargar: si un torneo ya tiene un resultado final escrito a mano, manda el manual.
- `pipeline/fuentes.json`: las fuentes (número de cada jugadora en Clippd, torneos del LET y de la RFEG).
- `pipeline/actualizar.py`: lee las fuentes y escribe `site/auto.js` (y `pipeline/estado.json`, lo que va aprendiendo).
- `pipeline/validar.mjs`: comprueba que todo carga antes de guardar. Si algo falla, no se guarda nada y la web se queda como estaba.
- `.github/workflows/actualizar.yml`: la actualización automática. Cada 2 horas, día y noche; solo guarda si hay novedades (y una vez al día para la fecha).

## Qué se actualiza solo (cada 2 horas, día y noche)

- **NCAA (Clippd Scoreboard):** los torneos de cada jugadora, también los futuros en cuanto su universidad se inscribe; los resultados, con vueltas, puesto y empates, y el marcador en directo mientras juegan. Los torneos que no estaban en la web se añaden solos a su calendario.
- **Ladies European Tour:** clasificación en directo y final de los torneos de `pipeline/fuentes.json` (ahora, el Open de España).
- **Ranking mundial amateur (WAGR):** el puesto de esta semana de cada jugadora de la NCAA y su histórico mensual.
- **RFEG:** las clasificaciones de los torneos apuntados en `pipeline/fuentes.json`.
- **Palmarés:** cada victoria o podio nuevo en un torneo individual se añade solo a sus logros; si un logro escrito a mano tenía mal el puesto, se corrige.
- **Estado de cada torneo** (próximo, en juego, pendiente, jugado) y la fecha «Actualizado».

Lo que dicen las fuentes oficiales manda sobre lo escrito a mano.

## Qué sigue siendo manual

- Jugadoras nuevas (en NCAA, además, su número de Clippd en `pipeline/fuentes.json`).
- Torneos nacionales y del Ladies European Tour: añadirlos a `pipeline/fuentes.json` con su enlace de resultados.
- Textos de perfil y logros que no salen de una clasificación.

## Lanzarla a mano

Pestaña **Actions** → **Actualizar resultados** → **Run workflow**. Marcando «Repasar toda la temporada» vuelve a leer la NCAA desde agosto.

## Configuración de Cloudflare Pages

- Framework preset: ninguno
- Build command: vacío
- Build output directory: `site`
- Rama de producción: `main`
