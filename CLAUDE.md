# agentflow-runtime (Python-форк Hermes)

🔴 ПЕРВЫМ ДЕЛОМ прочитай `~/Agent/WORKSPACE.md`.

Python-рантайм агента: `agent/ gateway/ plugins/(telegram) providers/ tui_gateway/ locales/ skills/ cli.py hermes_*.py scripts/install.sh`.
Крутится как k8s agent-под И как установка на ПК. **Перевод бота = `locales/ru.yaml`.**
Телеграм-бот = плагин гейтвея (`plugins/platforms/telegram/adapter.py → gateway.* → agent.*`) — НЕ резать.
Прод-образ строится ИЗ этого репо (решение B). upstream baseline — в FORK.md. Деплой только git push → CD.
