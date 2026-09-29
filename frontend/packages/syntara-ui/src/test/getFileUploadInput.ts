/**
 * Returns PatternFly FileUpload's hidden file input element.
 * PF does not expose the input via an accessible role or label by design.
 */
export function getFileUploadInput(container: ParentNode = document): HTMLInputElement {
  const input = container.querySelector('input[type="file"]')
  if (!(input instanceof HTMLInputElement)) {
    throw new Error('Expected hidden file input')
  }
  return input
}
