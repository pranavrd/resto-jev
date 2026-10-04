import { useEffect, useState } from 'react'
import { App } from './App'
import { PlacesApp } from './places/PlacesApp'

type View = 'places' | 'replay'

const fromHash = (): View => (window.location.hash === '#/replay' ? 'replay' : 'places')

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
      </nav>
      {view === 'places' ? <PlacesApp /> : <App />}
    </>
  )
}
