import { useStore } from '@nanostores/react'
import { FileText, RefreshCw } from 'lucide-react'
import { type CSSProperties } from 'react'

import { Button } from '../components/button'
import {
  $logPath,
  $mode,
  type BootstrapStateModel,
  openLogDir,
  startInstall,
  startUpdate
} from '../store'

interface FailureProps {
  bootstrap: BootstrapStateModel
}

/*
 * Failure screen. Same hero treatment as Welcome/Success — the wordmark
 * carries the brand, so we keep it across every terminal state.
 *
 * The actual error message lives below in muted text. Two affordances on
 * shared Button tokens: Retry (primary) and Open logs (quiet text link).
 */
export default function Failure({ bootstrap }: FailureProps) {
  const logPath = useStore($logPath)
  const mode = useStore($mode)
  const isUpdate = mode === 'update'

  return (
    <div className="hermes-fade-in flex h-full flex-col items-center justify-center gap-6 px-12 py-10">
      <div className="w-full max-w-2xl min-w-0 text-center">
        <p
          className="fit-text mx-auto mb-4 w-full font-['Collapse'] font-bold uppercase leading-[0.9] tracking-[0.08em] text-destructive mix-blend-plus-lighter dark:text-destructive/90"
          style={
            {
              '--fit-text-line-height': '0.9',
              '--fit-text-max': '5rem',
              '--fit-text-min': '2.25rem'
            } as CSSProperties
          }
        >
          <span>
            <span>{isUpdate ? '\u041e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u0438\u0435 \u043d\u0435 \u0437\u0430\u0432\u0435\u0440\u0448\u0438\u043b\u043e\u0441\u044c' : '\u0423\u0441\u0442\u0430\u043d\u043e\u0432\u043a\u0430 \u043d\u0435 \u0437\u0430\u0432\u0435\u0440\u0448\u0438\u043b\u0430\u0441\u044c'}</span>
          </span>
          <span aria-hidden="true">{isUpdate ? '\u041e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u0438\u0435 \u043d\u0435 \u0437\u0430\u0432\u0435\u0440\u0448\u0438\u043b\u043e\u0441\u044c' : '\u0423\u0441\u0442\u0430\u043d\u043e\u0432\u043a\u0430 \u043d\u0435 \u0437\u0430\u0432\u0435\u0440\u0448\u0438\u043b\u0430\u0441\u044c'}</span>
        </p>

        <p className="m-0 mx-auto max-w-xl text-center text-sm leading-normal tracking-tight text-muted-foreground">
          {bootstrap.error ??
            (isUpdate
              ? '\u0427\u0442\u043e-\u0442\u043e \u043f\u043e\u0448\u043b\u043e \u043d\u0435 \u0442\u0430\u043a \u0432\u043e \u0432\u0440\u0435\u043c\u044f \u043e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u0438\u044f.'
              : '\u0427\u0442\u043e-\u0442\u043e \u043f\u043e\u0448\u043b\u043e \u043d\u0435 \u0442\u0430\u043a \u0432\u043e \u0432\u0440\u0435\u043c\u044f \u0443\u0441\u0442\u0430\u043d\u043e\u0432\u043a\u0438.')}
        </p>
      </div>

      <div className="flex items-center gap-3">
        <Button className="gap-1.5" onClick={() => void (isUpdate ? startUpdate() : startInstall())}>
          <RefreshCw />
          {isUpdate ? '\u041f\u043e\u0432\u0442\u043e\u0440\u0438\u0442\u044c \u043e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u0438\u0435' : '\u041f\u043e\u0432\u0442\u043e\u0440\u0438\u0442\u044c \u0443\u0441\u0442\u0430\u043d\u043e\u0432\u043a\u0443'}
        </Button>
        <Button className="gap-1.5" onClick={() => void openLogDir()} variant="text">
          <FileText />
          \u041e\u0442\u043a\u0440\u044b\u0442\u044c \u043b\u043e\u0433\u0438
        </Button>
      </div>

      {logPath && (
        <p className="max-w-lg text-center text-xs text-muted-foreground/70">
          Лог: <code className="font-mono">{logPath}</code>
        </p>
      )}
    </div>
  )
}
