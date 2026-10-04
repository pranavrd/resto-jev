import { useEffect, useState } from 'react'
import { App } from './App'
import { PlacesApp } from './places/PlacesApp'
import { LabelApp } from './label/LabelApp'
import { ReviewApp } from './review/ReviewApp'

type View = 'places' | 'replay' | 'review' | 'label'

const fromHash = (): View => {
  const h = window.location.hash
  return h === '#/replay' ? 'replay' : h === '#/review' ? 'review' : h === '#/label' ? 'label' : 'places'
}

/** Switches between the places map and the walk replay. The hash keeps the view across reloads and in links. */
export function Shell() {
  const [view, setView] = useState<View>(fromHash)

  useEffect(() => {
    const onHash = () => setView(fromHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  const go = (v: View) => {
    window.location.hash = `#/${v}`
  }

  return (
    <>
      <nav className="viewswitch" aria-label="View">
        <button className={view === 'places' ? 'on' : ''} aria-pressed={view === 'places'} onClick={() => go('places')}>
          Places
        </button>
        <button className={view === 'replay' ? 'on' : ''} aria-pressed={view === 'replay'} onClick={() => go('replay')}>
          Walk replay
        </button>
        <button className={view === 'review' ? 'on' : ''} aria-pressed={view === 'review'} onClick={() => go('review')}>
          Review
        </button>
        <button className={view === 'label' ? 'on' : ''} aria-pressed={view === 'label'} onClick={() => go('label')}>
          Label
        </button>
      </nav>
      {view === 'places' ? <PlacesApp /> : view === 'review' ? <ReviewApp /> : view === 'label' ? <LabelApp /> : <App />}
    </>
  )
}
