# FORK baseline

Форк `nousresearch/hermes-agent`, из которого строится AgentFlow (runtime + app).

- **UPSTREAM_BASELINE**: `5d33efd9909f73dede49d7c49e497f8636aa486b`
  (`fmt(js): npm run fix on merge (#87599)`, 2026-08-16) — последний коммит Nous, от которого форкнулись.
- **upstream remote**: https://github.com/nousresearch/hermes-agent.git
- Все наши изменения — поверх этого коммита (на 2026-08-19 ещё в рабочем дереве, не закоммичены).

## Как тянуть upstream-фиксы (безопасности) после split
1. В `agentflow-runtime`/`agentflow-app` держать remote `upstream` → Nous.
2. `git fetch upstream`, дифф от `UPSTREAM_BASELINE` до нужного апстрим-коммита.
3. Черри-пикать точечно (мы дивержим по ребрендингу — прямой merge шумит). Обновить baseline здесь.
