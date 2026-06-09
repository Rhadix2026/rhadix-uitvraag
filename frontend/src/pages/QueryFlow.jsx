import Placeholder from './Placeholder'
export default function QueryFlow() {
  return (
    <Placeholder
      icon="🔎" title="Opvragen"
      sub="Het hart van de decentral-applicatie: indicatorresultaten opvragen bij zorgaanbieders via uitwisselprofielen en SPARQL."
      steps={[
        'Dataset selecteren',
        'Zorgaanbieder(s) kiezen (boomstructuur per zorgkantoor)',
        'Uitwisselprofiel + indicator(en) selecteren',
        'Parameters invullen en SPARQL-query uitvoeren',
        'Resultaten bekijken, vergelijken en exporteren',
      ]}
    />
  )
}
