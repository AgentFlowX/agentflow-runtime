import { cn } from '../lib/utils'

const assetPath = (path: string) => `${import.meta.env.BASE_URL}${path.replace(/^\/+/, '')}`

// Brand badge: the AgentFlow mark, identical in light/dark. The logo carries
// its own dark ground, so no background tile is applied. Asset lives in public/.
export function BrandMark({ className, ...props }: React.ComponentProps<'span'>) {
  return (
    <span className={cn('inline-flex size-14 shrink-0 items-center justify-center overflow-hidden rounded-xl', className)} {...props}>
      <img alt="AgentFlow" className="size-full object-contain" src={assetPath('agentflow-logo.png')} />
    </span>
  )
}
