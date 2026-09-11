import { SynLink } from '../SynLink'

import styles from './LinkCell.module.css'

/** Renders a table cell value as a client-side router link. */
export function LinkCell(props: Readonly<{ href: string; children: React.ReactNode }>) {
  return (
    <SynLink to={props.href} className={styles.root}>
      {props.children}
    </SynLink>
  )
}
