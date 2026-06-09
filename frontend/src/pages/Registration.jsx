import Placeholder from './Placeholder'
export default function Registration() {
  return (
    <Placeholder
      icon="🏢" title="Beheer / Registratie"
      sub="De beheermodule: organisaties, endpoints en DID-registratie binnen het KIK-V-netwerk beheren."
      steps={[
        'Organisatie registreren (naam, DID)',
        'Endpoints toevoegen en valideren',
        'Toegang en rollen beheren',
      ]}
    />
  )
}
