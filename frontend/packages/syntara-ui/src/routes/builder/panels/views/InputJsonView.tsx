import { SynCodeBlock } from '../../../../components/details/SynCodeBlock'

export type InputJsonViewProps = {
  data: Record<string, unknown> | null
}

export function InputJsonView({ data }: Readonly<InputJsonViewProps>) {
  if (!data) {
    return null
  }

  return (
    <section aria-label="JSON input">
      <SynCodeBlock jsonObject={data} enableCopy enableExpand expandTitle="Input JSON" noMaxHeight />
    </section>
  )
}
