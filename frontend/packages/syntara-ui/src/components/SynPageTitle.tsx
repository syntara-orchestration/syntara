import { toPageTitle } from '../utils/toPageTitle'

type SynPageTitleProps = {
  /** Title segments, most-specific first. The app name is appended automatically. */
  segments: (string | null | undefined)[]
}

/**
 * Sets the browser page `<title>`. Segments are joined with " | " and the
 * app name is appended automatically. Null, undefined, and blank segments
 * are filtered out. Place as the first child of `<SynPage>`.
 */
/* c8 ignore next -- V8 block coverage creates a phantom branch on the function declaration */
export function SynPageTitle({ segments }: Readonly<SynPageTitleProps>) {
  return <title>{toPageTitle(segments)}</title>
}
