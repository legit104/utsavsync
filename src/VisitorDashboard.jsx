
import { useEffect, useMemo, useState } from 'react'
import './VisitorDashboard.css'
import { api } from './api'
import dahiHandiProfile from './dahi_handi.json'

const fallbackLocations = [
  { id: 'lalbaugcha_raja', name: 'Lalbaugcha Raja', area: 'Lalbaug', lat: 18.994, lng: 72.8335, crowd: 42, capacity: 500, status: 'GREEN' },
  { id: 'siddhivinayak', name: 'Siddhivinayak Mandir', area: 'Prabhadevi', lat: 19.0169, lng: 72.8305, crowd: 73, capacity: 350, status: 'ORANGE' },
  { id: 'andheri_sports_complex', name: 'Andheri Sports Complex', area: 'Andheri West', lat: 19.12, lng: 72.835, crowd: 91, capacity: 800, status: 'RED' },
  { id: 'bandra_reclamation', name: 'Bandra Reclamation', area: 'Bandra West', lat: 19.045, lng: 72.819, crowd: 38, capacity: 600, status: 'GREEN' },
  { id: 'goregaon_ground', name: 'Goregaon Ground', area: 'Goregaon East', lat: 19.166, lng: 72.85, crowd: 66, capacity: 700, status: 'ORANGE' },
]

function VisitorDashboard({ onBackToLogin, userEmail, userRole = 'visitor', session }) {
  const [page, setPage] = useState(userRole === 'volunteer' ? 'Operations' : 'Dashboard')
  const [festival, setFestival] = useState('Ganesh Utsav')
  const [locations, setLocations] = useState(fallbackLocations)
  const [connected, setConnected] = useState(false)
  const [simTime, setSimTime] = useState('')
  const [apiMessage, setApiMessage] = useState('')
  const [swmTasks, setSwmTasks] = useState([])
  const [decisionLog, setDecisionLog] = useState([])
  const [swmRoutes, setSwmRoutes] = useState([])
  const [festivalProfiles, setFestivalProfiles] = useState([])
  const [whatIfResult, setWhatIfResult] = useState(null)
  const [simulationResult, setSimulationResult] = useState(null)
  const [scenario, setScenario] = useState({ action: 'close_site', site_id: '', at_time: '', extra_people: 250, then_advance_minutes: 60 })
  const [simulationEvents, setSimulationEvents] = useState(75)
  const [replaceLive, setReplaceLive] = useState(false)
  const [profileJson, setProfileJson] = useState('')
  const [groupSize, setGroupSize] = useState('4')
  const [preferred, setPreferred] = useState(fallbackLocations[0].name)
  const [arrival, setArrival] = useState('17:00')
  const [result, setResult] = useState(null)
  const [reports, setReports] = useState([])
  const [myGroups, setMyGroups] = useState([])
  const [reportType, setReportType] = useState('Crowd issue')
  const [crowdLevel, setCrowdLevel] = useState('HIGH')
  const [wasteFill, setWasteFill] = useState(85)
  const [entries, setEntries] = useState(0)
  const [exits, setExits] = useState(0)
  const [language, setLanguage] = useState('en')
  const [reportLocation, setReportLocation] = useState(fallbackLocations[0].name)
  const [reportDetails, setReportDetails] = useState('')

  const festivalId = festivalProfiles.find(profile => profile.name === festival)?.id
    || (festival === 'Navratri Garba' ? 'navratri_garba' : 'ganesh_utsav')
  const credentials = useMemo(() => ({
    accessToken: session?.access_token,
    userId: session?.user?.id || 'utsavsync-demo-user',
    role: userRole,
  }), [session?.access_token, session?.user?.id, userRole])

  useEffect(() => {
    let active = true
    api(`/festivals/${festivalId}/status`)
      .then(data => {
        if (!active) return
        setLocations(data.sites.map(site => ({
          id: site.id,
          name: site.name,
          area: site.facilities?.join(' · ') || 'Festival site',
          lat: site.lat, lng: site.lng, closed: site.closed,
          crowd: Math.round(site.occupancy * 100),
          capacity: site.capacity,
          forecast: Math.round(site.projected_next_slot_occupancy * 100),
          waste: Math.round((site.waste?.fill || 0) * 100),
          wasteForecast: Math.round((site.waste?.forecast_fill || 0) * 100),
          trend: site.trend_people_per_hour || 0,
          status: site.status === 'AMBER' ? 'ORANGE' : site.status,
        })))
        if (data.sites[0]) {
          setPreferred(current => data.sites.some(site => site.name === current) ? current : data.sites[0].name)
          setReportLocation(current => data.sites.some(site => site.name === current) ? current : data.sites[0].name)
        }
        setSimTime(data.sim_time)
        setArrival(data.sim_time)
        setConnected(true)
        setApiMessage('')
        Promise.all([
          api(`/festivals/${festivalId}/swm/tasks`),
          api(`/festivals/${festivalId}/swm/routes`),
          api(`/festivals/${festivalId}/log?limit=50`),
          api('/festivals'),
          api(`/festivals/${festivalId}/my-groups`, credentials),
        ]).then(([tasks, routes, entries, profiles, groups]) => {
          if (!active) return
          setSwmTasks(tasks)
          setSwmRoutes(routes)
          setDecisionLog([...entries].reverse())
          setFestivalProfiles(profiles)
          setMyGroups(groups)
          setScenario(current => ({ ...current, site_id: data.sites.some(site => site.id === current.site_id) ? current.site_id : data.sites[0]?.id || '' }))
        }).catch(() => {})
      })
      .catch(() => {
        if (!active) return
        setLocations(fallbackLocations)
        setConnected(false)
        setApiMessage('Backend is offline. Showing sample data; start the FastAPI server to use live festival state.')
      })
    return () => { active = false }
  }, [festivalId, credentials])

  async function refreshOperations() {
    const [status, tasks, routes, entries, groups] = await Promise.all([
      api(`/festivals/${festivalId}/status`),
      api(`/festivals/${festivalId}/swm/tasks`),
      api(`/festivals/${festivalId}/swm/routes`),
      api(`/festivals/${festivalId}/log?limit=50`),
      api(`/festivals/${festivalId}/my-groups`, credentials),
    ])
    setLocations(status.sites.map(site => ({ id: site.id, name: site.name,
      area: site.facilities?.join(' · ') || 'Festival site', lat: site.lat, lng: site.lng, crowd: Math.round(site.occupancy * 100),
      capacity: site.capacity, forecast: Math.round(site.projected_next_slot_occupancy * 100),
      waste: Math.round((site.waste?.fill || 0) * 100), wasteForecast: Math.round((site.waste?.forecast_fill || 0) * 100),
      trend: site.trend_people_per_hour || 0, status: site.status === 'AMBER' ? 'ORANGE' : site.status, closed: site.closed })))
    setSimTime(status.sim_time)
    setSwmTasks(tasks)
    setSwmRoutes(routes)
    setDecisionLog([...entries].reverse())
    setMyGroups(groups)
  }

  async function toggleSite(site) {
    try {
      setApiMessage('')
      await api(`/festivals/${festivalId}/sites/${site.id}/${site.closed ? 'open' : 'close'}`, {
        method: 'POST', ...credentials, body: { reason: 'Updated from UtsavSync volunteer console' },
      })
      await refreshOperations()
      setApiMessage(`${site.name} ${site.closed ? 'reopened' : 'closed'}; pending groups were re-evaluated.`)
    } catch (error) { setApiMessage(error.message) }
  }

  async function runRerouteDemo() {
    try {
      if (!connected) throw new Error('Reroute demo needs the Festival Operations Engine. Start the backend at http://localhost:8000, then refresh this page.')
      setApiMessage('')
      const demo = await api(`/festivals/${festivalId}/demo/reroute`, { method: 'POST', ...credentials })
      await refreshOperations()
      const rerouted = demo.reroutes?.length || 0
      const booked = demo.bookings?.filter(item => item.assigned).length || 0
      setApiMessage(rerouted
        ? `Live demo complete: ${rerouted} pending group(s) automatically rerouted after ${demo.site_name} turned ${demo.status_after}.`
        : `Surge reported at ${demo.site_name} (${demo.status_after}); ${booked} demo groups were booked, but none were pending in the reroute window. Reset the festival and try again.`)
      setPage('Decision Log')
    } catch (error) { setApiMessage(error.message) }
  }

  async function resetFestival() {
    try {
      if (!connected) throw new Error('Start the Festival Operations Engine before resetting the demo.')
      await api(`/festivals/${festivalId}/reset`, { method: 'POST', ...credentials })
      await refreshOperations()
      setApiMessage('Festival day reset to opening time. You can run the live reroute demo now.')
    } catch (error) { setApiMessage(error.message) }
  }

  async function completeTask(taskId) {
    try {
      await api(`/festivals/${festivalId}/swm/tasks/${taskId}/complete`, {
        method: 'POST', ...credentials, body: {},
      })
      await refreshOperations()
    } catch (error) { setApiMessage(error.message) }
  }

  async function runWhatIf(event) {
    event.preventDefault()
    try {
      const result = await api(`/festivals/${festivalId}/what-if`, {
        method: 'POST', ...credentials,
        body: { ...scenario, at_time: scenario.at_time || null, extra_people: Number(scenario.extra_people), then_advance_minutes: Number(scenario.then_advance_minutes) },
      })
      setWhatIfResult(result)
      setApiMessage('Scenario simulated on a copy. Live festival state was not changed.')
    } catch (error) { setApiMessage(error.message) }
  }

  async function runDaySimulation() {
    try {
      const result = await api(`/festivals/${festivalId}/simulate`, {
        method: 'POST', ...credentials,
        body: { events: Number(simulationEvents), replace_live: replaceLive },
      })
      setSimulationResult(result)
      if (replaceLive) await refreshOperations()
      setApiMessage(replaceLive ? 'Simulation completed and installed as the live demo state.' : 'Simulation completed. Live state was left unchanged.')
    } catch (error) { setApiMessage(error.message) }
  }

  async function advanceFestivalClock(minutes) {
    try {
      const result = await api(`/festivals/${festivalId}/clock/advance`, {
        method: 'POST', ...credentials, body: { minutes },
      })
      setSimTime(result.sim_time)
      await refreshOperations()
      setApiMessage(`Festival simulation advanced to ${result.sim_time}.`)
    } catch (error) { setApiMessage(error.message) }
  }

  async function addFestivalProfile(event) {
    event.preventDefault()
    try {
      const profile = JSON.parse(profileJson)
      const result = await api('/festivals', { method: 'POST', ...credentials, body: profile })
      const profiles = await api('/festivals')
      setFestivalProfiles(profiles)
      setFestival(profile.name)
      setProfileJson('')
      setApiMessage(result.message)
    } catch (error) {
      setApiMessage(error instanceof SyntaxError ? 'Profile must be valid JSON.' : error.message)
    }
  }

  const navigation = userRole === 'volunteer'
    ? ['Operations', 'Locations', 'Map', 'Reports', 'Waste Routes', 'What If', 'Simulation', 'Decision Log', 'Festival Profiles']
    : ['Dashboard', 'Locations', 'Map', 'Request Allocation', 'My Groups', 'Reports']

  async function requestAllocation(e) {
    e.preventDefault()
    const chosen = locations.find(item => item.name === preferred)
    const group = Number(groupSize)
    if (!group || group < 1) return
    setApiMessage('')
    try {
      if (!connected) throw new Error('The operations engine is offline. Start FastAPI and retry.')
      const response = await api(`/festivals/${festivalId}/requests`, {
        method: 'POST', ...credentials,
        body: { group_name: userEmail?.split('@')[0] || 'Festival visitors', group_size: group,
          preferred_site_id: chosen?.id, preferred_time: arrival },
      })
      const decision = response.decision
      setResult({ decision: decision.decision, reason: decision.reason,
        location: decision.assigned?.site_name || 'No allocation', group,
        projected: decision.assigned?.projected_occupancy, notifications: decision.notifications })
      const updated = await api(`/festivals/${festivalId}/status`)
      setSimTime(updated.sim_time)
      setMyGroups(await api(`/festivals/${festivalId}/my-groups`, credentials))
    } catch (error) {
      setApiMessage(error.message)
    }
  }

  async function submitReport(e) {
    e.preventDefault()
    setApiMessage('')
    const location = locations.find(item => item.name === reportLocation)
    const waste = reportType === 'Waste overflow'
    try {
      if (!connected) throw new Error('The operations engine is offline. Start FastAPI and retry.')
      const response = userRole === 'volunteer'
        ? await api(`/festivals/${festivalId}/field-reports`, {
          method: 'POST', ...credentials,
          body: { site_id: location?.id, crowd_level: waste ? null : crowdLevel,
            waste_level_percent: waste ? Number(wasteFill) : null, entries: Number(entries), exits: Number(exits),
            remarks: `${reportType}: ${reportDetails || 'No additional details supplied'}` },
        })
        : await api(`/festivals/${festivalId}/reports`, {
          method: 'POST', ...credentials,
          body: { site_id: location?.id, reporter_type: 'citizen',
            kind: waste ? 'waste' : 'crowd', ...(waste ? { bin_fill_percent: Number(wasteFill) } : { crowd_level: reportType === 'Safety concern' ? 'CRITICAL' : crowdLevel }),
            note: `${reportType}: ${reportDetails || 'No additional details supplied'}` },
        })
      setReports(prev => [{ id: Date.now(), type: reportType, location: reportLocation,
        details: reportDetails || 'Report submitted to the operations engine', decision: response.report?.decision }, ...prev])
      setReportDetails('')
      setPage('Reports')
      await refreshOperations()
    } catch (error) { setApiMessage(error.message) }
  }

  return (
    <div className="visitor-dashboard">
      <aside className="visitor-sidebar">
        <div className="brand">
          <span className="brand-icon">✺</span>
          <div>
            <h2>UtsavSync</h2>
            <small>FESTIVAL OPERATIONS ENGINE</small>
          </div>
        </div>

        <p className="side-label">{userRole === 'volunteer' ? 'VOLUNTEER MENU' : 'VISITOR MENU'}</p>
        {navigation.map(item => (
          <button
            key={item}
            className={`nav-item ${page === item ? 'active' : ''}`}
            onClick={() => setPage(item)}
          >
            <span>{{
              Dashboard: '⌂',
              'Request Allocation': '↗',
              'My Groups': '♧',
              Locations: '⌖',
              Reports: '▤',
              Operations: '⚙',
              'Decision Log': '☷',
            }[item]}</span>
            {item}
          </button>
        ))}

        <div className="sidebar-note">
          <span>✦</span>
          <strong>Celebrate safely.</strong>
          <p>Smarter crowd movement. Cleaner festivals.</p>
        </div>

        <button className="back-login" onClick={onBackToLogin}>
          ← Back to Login
        </button>
      </aside>

      <main className="visitor-main">
        <header className="visitor-topbar">
          <div>
            <p className="eyebrow">MUMBAI · FESTIVAL OPERATIONS</p>
            <h1>{{
              Dashboard: 'Your festival, made safer.',
              Operations: 'Volunteer operations center',
              'Request Allocation': 'Request a festival visit',
              'My Groups': 'Your group visits',
              Locations: 'Explore festival locations',
              Reports: userRole === 'volunteer' ? 'Submit a field report' : 'Report an issue',
              'Waste Routes': 'Coordinated waste pickup routes',
              'What If': 'Test an operations scenario',
              Simulation: 'Festival day simulation',
              'Festival Profiles': 'Festival configuration',
              'Decision Log': 'Engine decisions & reroutes',
            }[page]}</h1>
            <p>{userRole === 'volunteer' ? 'Volunteer workspace · crowd response, field reports and SWM coordination.' : 'Visitor workspace · plan your visit, follow crowd guidance and manage your group.'}</p>
          </div>
          <div className="visitor-profile">
            <span className="avatar">{userRole === 'volunteer' ? 'F' : 'V'}</span>
            <span>{userRole === 'volunteer' ? 'Volunteer' : userEmail || 'Visitor'}</span>
          </div>
        </header>

        <div className="demo-banner">
          {apiMessage || (connected ? `LIVE ENGINE · ${festival} · Simulated time ${simTime}` : 'DEMO MODE · Illustrative data only — not live BMC information')}
        </div>

        {page === 'Dashboard' && userRole === 'visitor' && (
          <>
            <section className="hero-panel">
              <div className="hero-copy">
                <span className="hero-tag">YOUR FESTIVAL COMPANION</span>
                <h2>Good celebrations start with a safer plan.</h2>
                <p>Check crowd levels, request a suitable location, and help keep festival areas clean.</p>
                <button className="primary-button" onClick={() => setPage('Request Allocation')}>
                  Request Allocation <span>→</span>
                </button>
              </div>
                <div className="hero-art" aria-hidden="true">
                  <span>✺</span>
                  <div>UTSAV<br />SYNC</div>
                  <small>SAFE · SMART · CLEAN</small>
                </div>
            </section>

            <section className="panel">
              <div className="section-heading">
                <div>
                  <p className="eyebrow">CHOOSE YOUR CELEBRATION</p>
                  <h2>Festival profiles</h2>
                </div>
              </div>
              <div className="festival-options">
                {(festivalProfiles.length ? festivalProfiles : [{ name: 'Ganesh Utsav' }, { name: 'Navratri Garba' }]).map((profile, index) => {
                  const item = profile.name
                  return (
                  <button
                    key={item}
                    className={`festival-card ${festival === item ? 'chosen' : ''}`}
                    onClick={() => setFestival(item)}
                  >
                    <span className="festival-symbol">{index === 0 ? 'ॐ' : '✺'}</span>
                    <span>
                      <strong>{item}</strong>
                      <small>{profile.description || (index === 0 ? 'Pandal visits & crowd guidance' : 'Festival sites & crowd guidance')}</small>
                    </span>
                    <span className="card-arrow">↗</span>
                  </button>
                  )
                })}
              </div>
            </section>

            <section className="panel">
              <div className="section-heading">
                <div>
                  <p className="eyebrow">CROWD SNAPSHOT</p>
                  <h2>Know before you go</h2>
                </div>
                <button className="text-button" onClick={() => setPage('Locations')}>All locations →</button>
              </div>
              <div className="status-grid">
                <div className="status-card green"><span>●</span><strong>{locations.filter(site => site.status === 'GREEN').length}</strong><small>GREEN · Normal</small></div>
                <div className="status-card orange"><span>●</span><strong>{locations.filter(site => site.status === 'ORANGE').length}</strong><small>AMBER · Busy</small></div>
                <div className="status-card red"><span>●</span><strong>{locations.filter(site => site.status === 'RED' || site.status === 'CLOSED').length}</strong><small>RED · Overcrowded</small></div>
              </div>
            </section>

            <section className="panel">
              <div className="section-heading">
                <div><p className="eyebrow">YOUR NEXT STEP</p><h2>How can we help?</h2></div>
              </div>
              <div className="quick-actions">
                <button onClick={() => setPage('Request Allocation')}><span>↗</span><strong>Request Allocation</strong><small>Submit your group and time</small></button>
                <button onClick={() => setPage('Locations')}><span>⌖</span><strong>Find a location</strong><small>Compare crowd levels</small></button>
                <button onClick={() => setPage('Reports')}><span>♻</span><strong>Report an issue</strong><small>Flag crowd or waste concerns</small></button>
              </div>
            </section>
          </>
        )}

        {page === 'Request Allocation' && (
          <section className="panel allocation-layout">
            <div className="allocation-intro">
              <span className="hero-tag">SMART VISIT PLANNER</span>
              <h2>Tell us about your visit.</h2>
              <p>UtsavSync checks your preferred location against illustrative crowd thresholds and suggests an action.</p>
              <div className="decision-key">
                <span className="green-dot" /> Allocate: suitable
                <span className="orange-dot" /> Divert: choose an alternative
                <span className="red-dot" /> Red: avoid allocation
              </div>
            </div>

            <form className="allocation-form" onSubmit={requestAllocation}>
              <label>Festival</label>
              <select value={festival} onChange={e => setFestival(e.target.value)}>
                {(festivalProfiles.length ? festivalProfiles.map(profile => profile.name) : ['Ganesh Utsav', 'Navratri Garba']).map(name => <option key={name}>{name}</option>)}
              </select>

              <label>Group size</label>
              <input type="number" min="1" max="100" value={groupSize} onChange={e => setGroupSize(e.target.value)} required />

              <label>Preferred location</label>
              <select value={preferred} onChange={e => setPreferred(e.target.value)}>
                {locations.map(item => (
                  <option key={item.name} value={item.name}>{item.name} · {item.status}</option>
                ))}
              </select>

              <label>Expected arrival time</label>
              <input type="time" value={arrival} onChange={e => setArrival(e.target.value)} required />

              <label>Decision message language</label>
              <select value={language} onChange={e => setLanguage(e.target.value)}><option value="en">English</option><option value="hi">हिन्दी</option><option value="mr">मराठी</option></select>

              <button className="primary-button full-button" type="submit">
                Check & Request Allocation →
              </button>
              <small className="form-note">The engine checks current occupancy, pending groups, capacity, festival hours, and crowd thresholds.</small>
            </form>

            {result && (
              <div className={`allocation-result ${result.decision === 'ALLOCATED' ? 'result-green' : result.decision === 'REJECTED' ? 'result-orange' : 'result-orange'}`}>
                <p className="eyebrow">ALLOCATION RECOMMENDATION</p>
                <h2>{result.decision}</h2>
                <p>{result.reason}</p>
                {result.notifications?.[language] && <p className="decision-notification">{result.notifications[language]}</p>}
                <div className="result-detail">
                  <span>Recommended location</span><strong>{result.location}</strong>
                  <span>Group size</span><strong>{result.group} people</strong>
                  <span>Arrival time</span><strong>{arrival}</strong>
                  <span>Festival profile</span><strong>{festival}</strong>
                </div>
                <small>{connected ? 'This allocation was evaluated by the rule-based festival engine.' : 'Start the operations engine to request a real allocation decision.'}</small>
              </div>
            )}
          </section>
        )}

        {page === 'My Groups' && (
          <section className="panel">
            <div className="section-heading"><div><p className="eyebrow">VISIT PLANS · {festival}</p><h2>Your group allocations</h2><p className="muted">Automatic reroutes and updated arrival details appear here.</p></div><button className="text-button" onClick={() => refreshOperations().catch(error => setApiMessage(error.message))}>Refresh ↻</button></div>
            {myGroups.length === 0 ? <div className="empty-state"><span>♧</span><strong>No groups allocated yet</strong><p>Submit a group request and the operations engine will recommend a safe site and time.</p><button className="primary-button" onClick={() => setPage('Request Allocation')}>Request a visit →</button></div> :
              <div className="group-list">{myGroups.map(group => <article className="group-card" key={group.id}>
                <div className="group-card-top"><div><span className="eyebrow">{group.id}</span><h3>{group.name}</h3></div><span className={`status-pill ${group.status === 'PENDING' ? 'green' : group.status === 'CANCELLED' ? 'red' : 'orange'}`}>{group.status}</span></div>
                <div className="group-details"><span>Site<strong>{group.site_name}</strong></span><span>Group<strong>{group.size} people</strong></span><span>Arrival<strong>{group.slot_time}</strong></span><span>Reroutes<strong>{group.reroutes || 0}</strong></span></div>
                {group.latest_update && <div className="decision-notification"><strong>{group.latest_update.decision}</strong> · {group.latest_update.reason}<p>{group.latest_update.notifications?.[language] || group.latest_update.notifications?.en}</p></div>}
              </article>)}</div>}
          </section>
        )}

        {page === 'Locations' && (
          <section className="panel">
            <div className="section-heading">
              <div><p className="eyebrow">LOCATION DIRECTORY</p><h2>Compare sites before travelling</h2></div>
              <span className="demo-label">{connected ? 'LIVE ENGINE DATA' : 'SAMPLE DATA'}</span>
            </div>
            <div className="location-list">
              {locations.map(item => (
                <article className="location-row" key={item.name}>
                  <div className={`location-thumbnail ${item.status.toLowerCase()}`}>✦</div>
                  <div className="location-details">
                    <strong>{item.name}</strong>
                    <small>⌖ {item.area} · Capacity {item.capacity} · Next slot {item.forecast ?? item.crowd}%</small>
                    <div className="capacity-track"><span className={item.status.toLowerCase()} style={{ width: `${item.crowd}%` }} /></div>
                    <small className="waste-readout">Bins {item.waste ?? 0}% · Forecast {item.wasteForecast ?? 0}% · Crowd trend {item.trend ?? 0}/hr</small>
                  </div>
                  <div className="location-status">
                    <span className={`status-pill ${item.status.toLowerCase()}`}>{item.status}</span>
                    <small>{item.crowd}% crowd level</small>
                  </div>
                  {userRole === 'volunteer' ? (
                    <button className="small-button" onClick={() => toggleSite(item)}>{item.closed ? 'Reopen site' : 'Close site'}</button>
                  ) : (
                    <button className="small-button" onClick={() => { setPreferred(item.name); setPage('Request Allocation'); setResult(null) }}>Request →</button>
                  )}
                </article>
              ))}
            </div>
            <p className="form-note">{connected ? 'Current status and occupancy are supplied by the Festival Operations Engine.' : 'Crowd values are sample data. Start the backend to load live engine state.'}</p>
          </section>
        )}

        {page === 'Map' && (
          <section className="panel">
            <div className="section-heading"><div><p className="eyebrow">SITE MAP · {festival}</p><h2>Festival locations &amp; crowd status</h2></div>
              <span className="demo-label">{connected ? `ENGINE · ${simTime}` : 'SAMPLE COORDINATES'}</span></div>
            <div className="map-layout">
              <div className="map-canvas" role="img" aria-label="Schematic map showing festival site positions and crowd levels">
                <div className="map-river"/><div className="map-road road-one"/><div className="map-road road-two"/><div className="map-road road-three"/>
                <span className="map-district district-one">MUMBAI</span><span className="map-district district-two">FESTIVAL ZONE</span>
                {(() => {
                  const latitudes = locations.map(site => site.lat || 19)
                  const longitudes = locations.map(site => site.lng || 72.85)
                  const minLat = Math.min(...latitudes), maxLat = Math.max(...latitudes)
                  const minLng = Math.min(...longitudes), maxLng = Math.max(...longitudes)
                  return locations.map(site => {
                    const x = maxLng === minLng ? 50 : 12 + ((site.lng - minLng) / (maxLng - minLng)) * 76
                    const y = maxLat === minLat ? 50 : 12 + ((maxLat - site.lat) / (maxLat - minLat)) * 76
                    return <button key={site.id} className={`map-pin ${site.status.toLowerCase()}`} style={{ left: `${x}%`, top: `${y}%` }} title={`${site.name} · ${site.crowd}% · ${site.status}`} onClick={() => { setPreferred(site.name); setPage('Locations') }}><i/ ><span>{site.name}</span></button>
                  })
                })()}
                <div className="map-legend"><span><i className="green"/>Green</span><span><i className="orange"/>Amber</span><span><i className="red"/>Red</span></div>
              </div>
              <div className="map-site-list">{locations.map(site => <article key={site.id} className="map-site-row"><span className={`status-dot ${site.status.toLowerCase()}`}/><div><strong>{site.name}</strong><small>{site.crowd}% · {site.status}</small></div></article>)}</div>
            </div>
            <p className="form-note">Map pins use the profile coordinates. This schematic map is for the prototype; use the location list for exact site details.</p>
          </section>
        )}

        {page === 'Reports' && (
          <section className="panel report-layout">
            <div>
              <p className="eyebrow">HELP KEEP FESTIVALS SAFE & CLEAN</p>
              <h2>What are you reporting?</h2>
              <p className="muted">Submit a crowd or waste observation for the operations team.</p>
              <form className="allocation-form" onSubmit={submitReport}>
                <label>Report type</label>
                <select value={reportType} onChange={e => setReportType(e.target.value)}>
                  <option>Crowd issue</option>
                  <option>Waste overflow</option>
                  <option>Blocked route</option>
                  <option>Safety concern</option>
                </select>
                <label>Location</label>
                <select value={reportLocation} onChange={e => setReportLocation(e.target.value)}>
                  {locations.map(item => <option key={item.name}>{item.name}</option>)}
                </select>
                {userRole === 'volunteer' && <>
                  {reportType !== 'Waste overflow' && <><label>Crowd reading</label><select value={crowdLevel} onChange={event => setCrowdLevel(event.target.value)}><option value="LOW">LOW</option><option value="MEDIUM">MEDIUM</option><option value="HIGH">HIGH</option><option value="CRITICAL">CRITICAL</option></select></>}
                  {reportType === 'Waste overflow' && <><label>Bin fill (%)</label><input type="number" min="0" max="150" value={wasteFill} onChange={event => setWasteFill(event.target.value)}/></>}
                  <div className="gate-count-fields"><div><label>People entered</label><input type="number" min="0" value={entries} onChange={event => setEntries(event.target.value)}/></div><div><label>People exited</label><input type="number" min="0" value={exits} onChange={event => setExits(event.target.value)}/></div></div>
                </>}
                <label>Additional details</label>
                <textarea rows="4" placeholder="Describe what you noticed..." value={reportDetails} onChange={e => setReportDetails(e.target.value)} />
                <button className="primary-button full-button" type="submit">Submit Report →</button>
              </form>
            </div>
            <div className="report-history">
              <p className="eyebrow">THIS SESSION</p>
              <h2>Submitted reports</h2>
              {reports.length === 0 ? <p className="muted">Reports submitted this session will appear here.</p> : reports.map(report => (
                <article className="report-item" key={report.id}>
                  <strong>{report.type}</strong>
                  <small>{report.location}</small>
                  <p>{report.details}</p>
                  <span className="status-pill orange">Sent to operations</span>
                </article>
              ))}
            </div>
          </section>
        )}

        {page === 'Operations' && userRole === 'volunteer' && (
          <section className="panel">
            <div className="section-heading">
              <div><p className="eyebrow">FESTIVAL CONTROL ROOM · {simTime || 'ENGINE OFFLINE'}</p><h2>Live operations</h2></div>
              <div className="ops-actions"><button className="primary-button" onClick={runRerouteDemo} disabled={!connected}>Run live surge &amp; reroute demo →</button><button className="small-button" onClick={resetFestival} disabled={!connected}>Reset festival day</button></div>
            </div>
            <div className="ops-intro"><span className="hero-tag">VOLUNTEER CONTROL ROOM</span><p>Monitor crowd safety, coordinate field reports and act on waste pickup tasks. The reroute demo books groups, triggers a critical crowd report, then shows the engine moving pending groups automatically.</p></div>
            <div className="status-grid">
              <div className="status-card green"><span>●</span><strong>{locations.filter(site => site.status === 'GREEN').length}</strong><small>GREEN · Normal sites</small></div>
              <div className="status-card orange"><span>●</span><strong>{locations.filter(site => site.status === 'ORANGE').length}</strong><small>AMBER · Busy sites</small></div>
              <div className="status-card red"><span>●</span><strong>{locations.filter(site => site.status === 'RED' || site.status === 'CLOSED').length}</strong><small>RED · Unsafe or closed</small></div>
            </div>
            <div className="clock-controls"><strong>Advance simulation clock</strong><span>Moves arrivals forward and updates crowd and waste forecasts.</span><div>{[30, 60, 180].map(minutes => <button className="small-button" key={minutes} onClick={() => advanceFestivalClock(minutes)} disabled={!connected}>+{minutes} min</button>)}</div></div>
            <div className="location-list">
              {locations.map(site => <article className="location-row" key={site.id}>
                <div className={`location-thumbnail ${site.status.toLowerCase()}`}>✦</div>
                <div className="location-details"><strong>{site.name}</strong><small>{site.crowd}% occupancy · {site.capacity} capacity</small>
                  <div className="capacity-track"><span className={site.status.toLowerCase()} style={{ width: `${site.crowd}%` }} /></div>
                </div>
                <span className={`status-pill ${site.status.toLowerCase()}`}>{site.closed ? 'CLOSED' : site.status}</span>
                {userRole === 'volunteer' && <button className="small-button" onClick={() => toggleSite(site)}>{site.closed ? 'Reopen' : 'Close site'}</button>}
              </article>)}
            </div>
            <div className="section-heading task-heading"><div><p className="eyebrow">SOLID WASTE MANAGEMENT</p><h2>Open pickup tasks</h2></div></div>
            {swmTasks.filter(task => task.status === 'OPEN').length === 0 ? <p className="muted">No open pickup tasks. The engine creates tasks when current or forecast bin fill reaches its configured trigger.</p> :
              swmTasks.filter(task => task.status === 'OPEN').map(task => <article className="report-item" key={task.id}>
                <strong>{task.site_name} · {task.priority} priority</strong><small>{task.expected_load_kg} kg forecast · {Math.round(task.current_fill * 100)}% bin fill now</small>
                <p>{task.reason}</p>{userRole === 'volunteer' && <button className="small-button" onClick={() => completeTask(task.id)}>Mark pickup complete</button>}
              </article>)}
          </section>
        )}

        {page === 'Waste Routes' && (
          <section className="panel">
            <div className="section-heading"><div><p className="eyebrow">SOLID WASTE MANAGEMENT</p><h2>Grouped pickup routes</h2></div><span className="demo-label">{swmRoutes.length} active route{swmRoutes.length === 1 ? '' : 's'}</span></div>
            {swmRoutes.length === 0 ? <div className="empty-state"><span>♻</span><strong>No open pickup route yet</strong><p>As crowd and bin reports arrive, the engine groups nearby pickup tasks into collection routes.</p></div> :
              <div className="route-grid">{swmRoutes.map(route => <article className="route-card" key={route.route_id}>
                <div className="route-card-header"><span className={`status-pill ${route.priority === 'URGENT' ? 'red' : 'orange'}`}>{route.priority}</span><strong>{route.route_id}</strong></div>
                <div className="route-metrics"><span><strong>{route.stops.length}</strong> stops</span><span><strong>{route.distance_km}</strong> km</span><span><strong>{route.expected_load_kg}</strong> kg</span></div>
                <ol className="route-stops">{route.stops.map((stop, index) => <li key={stop.task_id}><span>{index + 1}</span><div><strong>{stop.site_name}</strong><small>{stop.priority} pickup · {stop.task_id}</small></div></li>)}</ol>
              </article>)}</div>}
          </section>
        )}

        {page === 'What If' && (
          <section className="panel whatif-layout">
            <div><p className="eyebrow">SAFE SCENARIO TESTING</p><h2>What if plans change?</h2><p className="muted">Test a site closure or crowd surge on a copy of the engine. The live festival state stays untouched.</p>
              <form className="allocation-form" onSubmit={runWhatIf}>
                <label>Scenario</label><select value={scenario.action} onChange={event => setScenario({ ...scenario, action: event.target.value })}><option value="close_site">Close a site</option><option value="reopen_site">Reopen a site</option><option value="crowd_surge">Sudden crowd surge</option></select>
                <label>Festival site</label><select value={scenario.site_id} onChange={event => setScenario({ ...scenario, site_id: event.target.value })}>{locations.map(site => <option key={site.id} value={site.id}>{site.name}</option>)}</select>
                <label>Scenario time (optional)</label><input type="time" value={scenario.at_time} onChange={event => setScenario({ ...scenario, at_time: event.target.value })}/>
                {scenario.action === 'crowd_surge' && <><label>Additional people</label><input type="number" min="0" value={scenario.extra_people} onChange={event => setScenario({ ...scenario, extra_people: event.target.value })}/></>}
                <label>Then advance (minutes)</label><input type="number" min="0" max="1440" value={scenario.then_advance_minutes} onChange={event => setScenario({ ...scenario, then_advance_minutes: event.target.value })}/>
                <button className="primary-button full-button" type="submit">Run what-if scenario →</button>
              </form>
            </div>
            <div className="scenario-result">{whatIfResult ? <><span className="hero-tag">LIVE STATE UNCHANGED</span><h3>Scenario results</h3><p>{whatIfResult.note}</p><div className="scenario-summary">{Object.entries(whatIfResult.summary).map(([key, value]) => <span key={key}><strong>{value}</strong>{key}</span>)}</div><h4>Projected site conditions</h4>{whatIfResult.sites_after.map(site => <article className="scenario-site" key={site.id}><strong>{site.name}</strong><span className={`status-pill ${site.status === 'AMBER' ? 'orange' : site.status.toLowerCase()}`}>{site.status}</span><small>{Math.round(site.occupancy * 100)}% occupancy · {Math.round(site.waste.forecast_fill * 100)}% forecast bin fill</small></article>)}</> : <div className="empty-state"><span>◷</span><strong>Compare a possible future</strong><p>Choose a scenario to see who would be rerouted and which sites may become unsafe.</p></div>}</div>
          </section>
        )}

        {page === 'Simulation' && (
          <section className="panel">
            <div className="section-heading"><div><p className="eyebrow">FESTIVAL DAY PLAYBACK</p><h2>Run a day simulation</h2><p className="muted">Generate realistic group requests, crowd and waste reports against the selected festival rules.</p></div></div>
            <div className="simulation-controls"><label>Events to simulate<select value={simulationEvents} onChange={event => setSimulationEvents(event.target.value)}><option value="50">50 events</option><option value="75">75 events</option><option value="100">100 events</option></select></label><label className="remember-label"><input type="checkbox" checked={replaceLive} onChange={event => setReplaceLive(event.target.checked)}/> Replace current live demo state</label><button className="primary-button" onClick={runDaySimulation}>Run simulation →</button></div>
            {simulationResult && <div className="simulation-result"><div className="simulation-stats">{Object.entries(simulationResult.summary).filter(([, value]) => typeof value === 'number').map(([key, value]) => <div className="status-card orange" key={key}><strong>{value}</strong><small>{key.replaceAll('_', ' ')}</small></div>)}</div><p>{simulationResult.summary.total_inputs} events · {simulationResult.status.sites.length} sites · simulated time {simulationResult.status.sim_time}</p><details><summary>View full simulation summary</summary><pre>{JSON.stringify(simulationResult.summary, null, 2)}</pre></details></div>}
          </section>
        )}

        {page === 'Festival Profiles' && (
          <section className="panel">
            <div className="section-heading"><div><p className="eyebrow">CONFIGURATION-DRIVEN FESTIVALS</p><h2>Festival profiles</h2><p className="muted">Add a new festival by uploading a JSON profile; the engine applies the same rules without code changes.</p></div></div>
            <div className="profile-grid">{festivalProfiles.map(profile => <article className="profile-card" key={profile.id}><span className="festival-symbol">✺</span><div><strong>{profile.name}</strong><small>{profile.sites} sites · {profile.hours?.start}–{profile.hours?.end}</small><p>{profile.description}</p></div><button className="small-button" onClick={() => setFestival(profile.name)}>Open profile</button></article>)}</div>
            {userRole === 'volunteer' && <form className="profile-upload" onSubmit={addFestivalProfile}><label htmlFor="festival-json">Add festival profile JSON</label><p className="muted">A five-site Dahi Handi profile is included as a ready-to-add example.</p><textarea id="festival-json" rows="10" value={profileJson} onChange={event => setProfileJson(event.target.value)} placeholder={'Paste a FestivalProfile JSON document here…\nRequired: id, name, day, waste, sites'} /><div className="profile-actions"><button className="small-button" type="button" onClick={() => setProfileJson(JSON.stringify(dahiHandiProfile, null, 2))}>Load Dahi Handi example</button><button className="primary-button" type="submit">Add profile to engine →</button></div></form>}
          </section>
        )}

        {page === 'Decision Log' && userRole === 'volunteer' && (
          <section className="panel">
            <div className="section-heading"><div><p className="eyebrow">AUDIT TRAIL · {festival}</p><h2>Recent engine decisions</h2></div>
              <div className="ops-actions"><button className="primary-button" onClick={runRerouteDemo} disabled={!connected}>Trigger crowd surge demo →</button><button className="small-button" onClick={resetFestival} disabled={!connected}>Reset day</button></div></div>
            {decisionLog.length === 0 ? <p className="muted">No decisions recorded yet. Run the live surge demo to see automatic rerouting here.</p> :
              decisionLog.map((entry, index) => <article className="report-item" key={entry.id || `${entry.type}-${index}`}>
                <strong>{entry.decision || entry.type} · {entry.sim_time}</strong>
                <small>{entry.site_name || entry.reason?.split('.')[0]}</small>
                <p>{entry.reason}</p>
              </article>)}
          </section>
        )}

        <footer className="visitor-footer">
          <span>UtsavSync · Festival Operations Engine</span>
          <span>{connected ? 'Connected to the Festival Operations Engine' : 'Sample data · Start the backend for live operations'}</span>
        </footer>
      </main>
    </div>
  )
}

export default VisitorDashboard
