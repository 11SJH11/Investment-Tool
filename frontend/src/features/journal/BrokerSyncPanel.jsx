import BrokerProfilesPanel from '../brokers/BrokerProfilesPanel';
export default function BrokerSyncPanel({onSynced}) { return <BrokerProfilesPanel destination="journal" onSynced={onSynced}/>; }
