import tableLayoutStyles from './expandableListTable.module.css'

type ExpandableListTableColGroupProps = {
  /** Includes a narrow column before the expand column for bulk row selection. */
  withSelect?: boolean
  /** Number of data columns after the leading control columns. */
  dataColumnCount: number
}

/** Keeps expand (and optional select) columns from consuming excess width in expandable list tables. */
export function ExpandableListTableColGroup({
  withSelect = false,
  dataColumnCount,
}: Readonly<ExpandableListTableColGroupProps>) {
  return (
    <colgroup>
      {withSelect ? <col className={tableLayoutStyles.controlCol} /> : null}
      <col className={tableLayoutStyles.controlCol} />
      {Array.from({ length: dataColumnCount }, (_, index) => (
        <col key={`data-col-${index}`} />
      ))}
    </colgroup>
  )
}
