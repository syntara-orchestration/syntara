import styles from './SynStepHeader.module.css'

export function SynStepHeader(props: Readonly<{ children: React.ReactNode; className?: string }>) {
  return (
    <div data-testid="node-header" className={[styles.root, props.className].filter(Boolean).join(' ')}>
      {props.children}
    </div>
  )
}
