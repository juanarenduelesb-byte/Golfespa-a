# Españolas · Golf femenino

Las golfistas españolas en la NCAA (EE. UU.) y en el circuito nacional: calendario, resultados, marcador en vivo y ranking.

## Cómo está montado

- `site/`: la web. Es estática (un solo `index.html` con los datos dentro) y la publica Cloudflare Pages cada vez que cambia algo en la rama `main`.
- `site/auto.js`: los resultados que se leen solos. Lo escribe la actualización; no se edita a mano. La web lo mezcla con sus datos al cargar: si un torneo ya tiene un resultado final escrito a mano, manda el manual.
- `pipeline/feeds.json`: la lista de torneos que se leen solos, con la dirección de su clasificación.
- `pipeline/actualizar.py`: lee esas clasificaciones, empareja a las jugadoras por nombre y escribe `site/auto.js`.
- `pipeline/validar.mjs`: comprueba que todo carga antes de guardar. Si algo falla, no se guarda nada y la web se queda como estaba.
- `.github/workflows/actualizar.yml`: la actualización automática. Pasada cada mañana (6:23 en invierno) y cada 2 horas durante el día; las pasadas sin torneos en juego terminan en segundos sin tocar nada.

## Qué se actualiza solo

- La fecha de «Actualizado», cada mañana.
- El estado de cada torneo (próximo, en juego, pendiente, jugado): sale de las fechas, la propia web lo calcula.
- Los resultados de los torneos que están en `pipeline/feeds.json`, mientras se juegan y hasta 3 días después.

Fuentes que ya se leen: clasificaciones de la RFEG (`rfegolf.livegolfscoring.es`, `mitarjeta.golf`).

## Qué sigue siendo manual

Añadir un torneo nuevo, una jugadora nueva o un texto de logros se hace en `site/index.html`. Para que un torneo se lea solo, añade una línea a `pipeline/feeds.json`:

```json
{"event": "id-del-torneo", "mode": "nac", "type": "lgs", "a": "2027-03-02", "b": "2027-03-07", "url": "https://rfegolf.livegolfscoring.es/torneos/clasificacion/NNN"}
```

## Lanzarla a mano

Pestaña **Actions** → **Actualizar resultados** → **Run workflow**.

## Configuración de Cloudflare Pages

- Framework preset: ninguno
- Build command: vacío
- Build output directory: `site`
- Rama de producción: `main`
