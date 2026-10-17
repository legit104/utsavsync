import { useEffect, useRef } from 'react'
import { CircleMarker, MapContainer, Pane, Popup, TileLayer, Tooltip, useMap } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import './SiteMap.css'

const STATUS_COLORS = { GREEN: '#2fa56f', AMBER: '#ee9b1d', RED: '#df5c55', CLOSED: '#8790a0' }
const MUMBAI = [19.076, 72.8777]

function statusOf(site) {
  return site.closed ? 'CLOSED' : site.status
}

/* Fit every site in view when the festival (its set of sites) changes, not on each data refresh. */
function FitToSites({ sites }) {
  const map = useMap()
  const key = sites.map(site => site.id).join('|')
  useEffect(() => {
    if (!sites.length) return
    if (sites.length === 1) map.setView([sites[0].lat, sites[0].lng], 15)
    else map.fitBounds(sites.map(site => [site.lat, site.lng]), { padding: [40, 40], maxZoom: 15 })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, map])
  return null
}

/* Fly to a site picked from the list and open its details. */
function FocusSite({ site, markers }) {
  const map = useMap()
  useEffect(() => {
    if (!site) return
    map.flyTo([site.lat, site.lng], Math.max(map.getZoom(), 15), { duration: 0.6 })
    const timer = setTimeout(() => markers.current[site.id]?.openPopup(), 650)
    return () => clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [site?.id, map])
  return null
}

/* Each status draws in its own map layer, stacked by severity, so a nearby GREEN or
   AMBER site can never hide a RED or CLOSED one (Leaflet panes, above the map tiles). */
const STATUS_PANES = [['GREEN', 410], ['AMBER', 420], ['RED', 430], ['CLOSED', 440]]

function SiteMap({ sites, selectedId, onSelect, renderActions }) {
  const markers = useRef({})
  const located = sites.filter(site => Number.isFinite(site.lat) && Number.isFinite(site.lng))
  const selected = located.find(site => site.id === selectedId)

  return (
    <div className="site-map">
      <MapContainer center={MUMBAI} zoom={12} scrollWheelZoom={false} className="site-map-canvas">
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <FitToSites sites={located} />
        <FocusSite site={selected} markers={markers} />
        {STATUS_PANES.map(([paneStatus, zIndex]) => (
          <Pane key={paneStatus} name={'sites-' + paneStatus.toLowerCase()} style={{ zIndex }}>
            {located.filter(site => statusOf(site) === paneStatus).map(site => {
              const status = statusOf(site)
              const isSelected = site.id === selectedId
              return (
                <CircleMarker
                  key={site.id + ':' + status}
                  ref={marker => { markers.current[site.id] = marker }}
                  center={[site.lat, site.lng]}
                  radius={isSelected ? 15 : 11}
                  pathOptions={{ color: '#ffffff', weight: 3, fillColor: STATUS_COLORS[status] || STATUS_COLORS.GREEN, fillOpacity: 0.95 }}
                  eventHandlers={{ click: () => onSelect?.(site.id) }}
                >
                  <Tooltip direction="top" offset={[0, -12]}>{site.name} · {site.crowd}%</Tooltip>
                  <Popup>
                    <div className="site-popup">
                      <strong>{site.name}</strong>
                      <span className={`status-pill ${status.toLowerCase()}`}>{status}</span>
                      <dl>
                        <dt>Crowd now</dt><dd>{site.crowd}% of {site.capacity}</dd>
                        {site.forecast !== undefined && <><dt>Next slot</dt><dd>{site.forecast}%</dd></>}
                        {site.waste !== undefined && <><dt>Bins</dt><dd>{site.waste}% · forecast {site.wasteForecast ?? site.waste}%</dd></>}
                      </dl>
                      {renderActions?.(site)}
                    </div>
                  </Popup>
                </CircleMarker>
              )
            })}
          </Pane>
        ))}
      </MapContainer>
      <div className="site-map-legend" aria-hidden="true">
        <span><i style={{ background: STATUS_COLORS.GREEN }} />Green</span>
        <span><i style={{ background: STATUS_COLORS.AMBER }} />Amber</span>
        <span><i style={{ background: STATUS_COLORS.RED }} />Red</span>
        <span><i style={{ background: STATUS_COLORS.CLOSED }} />Closed</span>
      </div>
    </div>
  )
}

export default SiteMap
