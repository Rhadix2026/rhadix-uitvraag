import { Page, PageTitle, Card } from '../components/UI'

export default function Placeholder({ icon, title, sub, steps = [], note }) {
  return (
    <Page>
      <PageTitle badge="Gepland" title={`${icon} ${title}`} sub={sub} />
      {steps.length > 0 && (
        <Card style={{ marginBottom: 20 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text2)', textTransform: 'uppercase', letterSpacing: '.5px', marginBottom: 14 }}>Voorziene flow</div>
          <ol style={{ listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 10, counterReset: 'step' }}>
            {steps.map((s, i) => (
              <li key={i} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <span style={{ width: 26, height: 26, borderRadius: '50%', background: 'var(--blue-light)', color: 'var(--blue)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: 13, flexShrink: 0 }}>{i + 1}</span>
                <span style={{ fontSize: 14, color: 'var(--text2)' }}>{s}</span>
              </li>
            ))}
          </ol>
        </Card>
      )}
      <Card style={{ background: 'var(--blue-light)', border: '1px solid var(--blue-mid)' }}>
        <div style={{ fontSize: 14, color: 'var(--blue-dark)' }}>
          {note || 'Deze module is nog niet geïmplementeerd. De shell en navigatie staan klaar; functionaliteit volgt in een volgende mijlpaal.'}
        </div>
      </Card>
    </Page>
  )
}
