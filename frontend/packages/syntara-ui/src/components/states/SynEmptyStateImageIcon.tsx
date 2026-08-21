import styles from './SynEmptyStateImageIcon.module.css'

/** Renders a custom image in place of the default PF icon inside an EmptyState. */
export function SynEmptyStateImageIcon({ src, alt }: Readonly<{ src: string; alt?: string }>) {
  return <img src={src} alt={alt} className={styles.imageIcon} />
}
