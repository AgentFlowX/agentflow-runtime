import { defineLocale } from './define-locale'
import { ruPart1 } from './ru-part1'
import { ruPart2 } from './ru-part2'
import { ruPart3 } from './ru-part3'
import { ruPart4 } from './ru-part4'
import { ruPart5 } from './ru-part5'

// Полная русская локаль AgentFlow. Собрана из пяти частей (переведённые
// верхнеуровневые группы каталога en). Части не пересекаются по группам,
// поэтому верхнеуровневый spread склеивает их без потерь; defineLocale затем
// глубоко мёржит поверх английской базы (страховка от пропущенных ключей).
export const ru = defineLocale({
  ...ruPart1,
  ...ruPart2,
  ...ruPart3,
  ...ruPart4,
  ...ruPart5,
  quickEntry: {
    currentChat: 'Текущий чат',
    newSession: 'Новая сессия',
    ask: 'Спросите AgentFlow…',
    notConnected: 'Нет связи — откройте AgentFlow, чтобы переподключиться',
  },
})
