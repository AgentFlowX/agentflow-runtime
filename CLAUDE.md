# hermes (моно-репо: Python-рантайм + Electron/Tauri-приложение)

🔴 ПЕРВЫМ ДЕЛОМ прочитай `~/Agent/WORKSPACE.md`.

Это восстановленный моно-репо upstream Hermes: Python-рантайм и десктоп-клиент
лежат бок о бок в корне (как в upstream). upstream baseline — в FORK.md.
Деплой только git push → CD.

## Python runtime (agent/ gateway/ plugins/ providers/ tui_gateway/ locales/ skills/ cli.py hermes_*.py)

Python-рантайм агента: `agent/ gateway/ plugins/(telegram) providers/ tui_gateway/ locales/ skills/ cli.py hermes_*.py scripts/install.sh`.
Крутится как k8s agent-под И как установка на ПК. **Перевод бота = `locales/ru.yaml`.**
Телеграм-бот = плагин гейтвея (`plugins/platforms/telegram/adapter.py → gateway.* → agent.*`) — НЕ резать.
Прод-образ строится ИЗ этого репо (решение B).

## Desktop app (apps/ web/ ui-tui/)

Клиентское приложение для ПК: `apps/desktop apps/bootstrap-installer apps/shared web ui-tui`.
«Звонит» рантайму по протоколу (`apps/desktop/src/types/hermes.ts`), Python внутрь НЕ бандлит.
i18n приложения = `apps/desktop/src/i18n/ru.ts` (отдельно от рантайм-locales).
