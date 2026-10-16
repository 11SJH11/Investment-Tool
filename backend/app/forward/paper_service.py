"""Backend-owned paper monitoring and explicit, bounded user controls."""
import json
from threading import Event,Thread
from .paper_client import PaperClient
from .paper_gateway import PaperGateway
from .paper_coordinator import PaperCoordinator
from .paper_protection import ACK
from .bars import stamp


class PaperService:
    def __init__(self,database,settings,runtime,*,client=None,start_thread=True,clock=None):
        self.database=database;self.stop=Event();self.thread=None;self.next_poll=0
        self.client=client or (PaperClient(settings.alpaca_api_key,settings.alpaca_api_secret) if settings.alpaca_configured else None)
        self.gateway=PaperGateway(database,self.client,**({'clock':clock} if clock else {}))
        self.coordinator=PaperCoordinator(database,runtime,self.gateway)
        if start_thread:
            self.thread=Thread(target=self._loop,name='forward-paper',daemon=True);self.thread.start()

    def close(self):
        self.stop.set()
        if self.thread:self.thread.join(timeout=20)
        if self.client:self.client.close()

    def _loop(self):
        while not self.stop.wait(5):
            try:self.tick()
            except Exception:pass  # Per-deployment failures are durable/sanitized.

    def _items(self):
        with self.database.connect() as c:return [json.loads(r[0]) for r in c.execute('SELECT document FROM forward_paper')]

    def create(self,experiment,risk):
        if not self.client:raise ValueError('Configure Alpaca paper credentials first')
        return self.gateway.create(experiment,risk)['id']

    def control(self,identifier,action,acknowledgement=None):
        if action=='disarm':return self.gateway.disarm(identifier)
        if not self.client:raise ValueError('Configure Alpaca paper credentials first')
        if action=='arm':return self.coordinator.arm(identifier,acknowledgement)
        if action=='cancel':return self.gateway.cancel_open(identifier)
        if action=='flatten':
            self.gateway.disarm(identifier,'explicit_flatten')
            return self.coordinator.protection.request_exit(identifier,'explicit_flatten')
        raise ValueError('Unknown paper control')

    def disarm_all(self):
        for item in self._items():self.gateway.disarm(item['id'],'global_disarm')

    def tick(self):
        if not self.client or self.stop.is_set():return
        current=stamp(self.gateway.clock()).timestamp()
        if current<self.next_poll:return
        self.next_poll=current+5
        for item in self._items():
            if not item['account_id'] and not item['armed']:continue
            try:self.coordinator.tick(item['id'])
            except Exception as exc:
                self.gateway.disarm(item['id'],'paper_monitor_requires_review')
                retry=getattr(exc,'retry_after',None)
                if retry:
                    self.next_poll=max(self.next_poll,current+min(3600,max(5,retry)))
                    break

    def report(self):
        # No credentials, raw broker account IDs, arbitrary provider payloads or
        # signing capabilities cross the frontend boundary.
        fields=('id','experiment_id','mode','symbol','strategy_key','risk','armed','reconciled',
                'position_qty','account_equity','reconciled_at','last_error','close_protection','start_after')
        return dict(configured=self.client is not None,acknowledgement=ACK,
                    limitation='Paper only. Post-fill and cancellation/replacement gaps are unprotected. Closing orders are not guaranteed fills. Keep monitoring broker state.',
                    items=[{k:item.get(k) for k in fields} for item in self._items()])
