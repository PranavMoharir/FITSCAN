import { useEffect } from 'react'

/** Sets the browser tab title to "<title> · FITSCAN" while the page is shown. */
export function useDocumentTitle(title: string | undefined) {
  useEffect(() => {
    if (title) document.title = `${title} · FITSCAN`
  }, [title])
}
